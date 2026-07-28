"""Core ETF permission diagnostics — why core_etf_permission is RESTRICTED."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.execution_scope import count_dry_run_days
from src.report.authoritative_status import resolve_authoritative_execution
from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json

DIAGNOSTICS_JSON = "outputs/core_etf_permission_diagnostics.json"
TRACE_CSV = "outputs/core_etf_candidate_trace.csv"
ETF_ONLY_NOTE = "ETF_ONLY is execution scope constraint — not ETF buy permission."


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _weight_map(output_dir: Path) -> dict[str, dict[str, str]]:
    by_ticker: dict[str, dict[str, str]] = {}
    for row in _read_csv_rows(output_dir / "current_vs_target.csv"):
        t = _normalize_ticker(row.get("ticker", ""))
        if t:
            by_ticker[t] = row
    return by_ticker


def list_etf_underweight_candidates(final_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Underweight ETF Wait rows from final_execution_decision (shared with counterfactual)."""
    rows: list[dict[str, Any]] = []
    for row in final_doc.get("allowed_actions") or []:
        action = str(row.get("action") or "")
        reason = str(row.get("reason") or "")
        ticker = _normalize_ticker(row.get("ticker", ""))
        if not ticker or ticker == "CASH":
            continue
        is_under = action == "Wait" and (
            "underweight" in reason.lower() or "Underweight" in reason
        )
        if action in {"Buy", "Add", "BuyCandidate", "Buy-allowed"}:
            is_under = True
        if not is_under:
            continue
        rows.append({
            "ticker": ticker,
            "name": str(row.get("name") or ""),
            "action": action,
            "allowed_size_pct": float(row.get("allowed_size_pct") or 0),
            "reason": reason,
            "priority": str(row.get("priority") or ""),
        })
    return rows


def _data_gate_context(
    data_dir: Path,
    output_dir: Path,
    *,
    final_doc: dict[str, Any],
    log: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc)
    unified = str(auth.get("unified_data_gate") or final_doc.get("data_gate") or "YELLOW")
    reasons: list[str] = []
    fixes: list[str] = []

    detail = log.get("data_gate_detail") or {}
    for driver in detail.get("drivers") or []:
        reasons.append(str(driver))

    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("id") == "AC-02":
            ac_detail = item.get("detail") or {}
            for r in ac_detail.get("fail_reasons") or []:
                if r not in reasons:
                    reasons.append(str(r))

    audit = final_doc.get("market_data_audit") or log.get("market_data_audit") or {}
    for issue in audit.get("issues") or []:
        tag = f"market_data_audit:{issue}"
        if tag not in reasons:
            reasons.append(tag[:200])

    if unified == "YELLOW" and not reasons:
        reasons.append("unified_data_gate=YELLOW")
    if unified == "YELLOW":
        fixes.append("Resolve unified_data_gate YELLOW drivers before core_etf can become ALLOWED")
    if any("health_gate" in r for r in reasons):
        fixes.append("Clear health_gate YELLOW contributors (tier2 stale, price coverage)")
    if any("alpha_gate" in r for r in reasons):
        fixes.append("Alpha gate YELLOW contributes to unified YELLOW — does not block ETF alone but lifts data_gate")
    if audit.get("reanalysis_required"):
        fixes.append("Refresh mixed-staleness market fields flagged in market_data_audit")

    return unified, reasons, fixes


def decompose_core_etf_restriction(
    *,
    execution_scope: str,
    core_price_gate_status: str,
    health_gate: str,
    data_gate: str,
    portfolio_gate: str,
    policy_permissions: dict[str, str],
    policy_cap_active: bool,
    dry_run_days: int,
    dry_run_required: int,
    actual_buy_allowed: int,
    core_etf_permission: str,
) -> list[str]:
    reasons: list[str] = []
    if execution_scope == "NO_TRADE":
        reasons.append("execution_scope=NO_TRADE")
    if core_price_gate_status == "fail":
        reasons.append("core_price_gate=fail")
    if health_gate == "RED":
        reasons.append("health_gate=RED")
    elif health_gate == "YELLOW":
        reasons.append("health_gate=YELLOW")
    if data_gate == "RED":
        reasons.append("data_gate=RED")
    elif data_gate == "YELLOW":
        reasons.append("data_gate=YELLOW→core_etf_REVIEW_ONLY")
    if portfolio_gate == "RED":
        reasons.append("portfolio_gate=RED")
    if policy_cap_active:
        reasons.append("policy_cap_active")
    etf_new = str(policy_permissions.get("etf_new_buy") or "")
    if etf_new == "BLOCKED":
        reasons.append("etf_new_buy=BLOCKED")
    elif etf_new == "REVIEW_ONLY":
        reasons.append("etf_new_buy=REVIEW_ONLY")
    if dry_run_days < dry_run_required:
        reasons.append(f"dry_run_incomplete={dry_run_days}/{dry_run_required}")
    if actual_buy_allowed <= 0:
        reasons.append("actual_buy_allowed=0")
    if core_etf_permission == "RESTRICTED" and not reasons:
        reasons.append("core_etf_composite_REVIEW_ONLY")
    if core_etf_permission == "BLOCKED" and not reasons:
        reasons.append("core_etf_blocked")
    return reasons


def build_core_etf_permission_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    perms = final_doc.get("execution_permissions") or {}
    gates = perms.get("gates") or {}
    policy_cap = final_doc.get("policy_cap") or {}
    policy_permissions = dict(perms.get("policy_permissions") or {})

    log: dict[str, Any] = {}
    log_path = output_dir / "decision_log.jsonl"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            log = json.loads(lines[-1])

    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc)
    metrics = count_executable_actions(final_doc)
    actual_buy = int(metrics.get("actual_buy_allowed_count") or 0)

    shadow = read_output_json(output_dir / "shadow_diagnostic.json") or {}
    dry_run_required = int((shadow.get("gates") or {}).get("dry_run_required") or 10)
    dry_run_days = count_dry_run_days(output_dir)

    data_gate = str(final_doc.get("data_gate") or gates.get("data_gate") or "YELLOW")
    unified_gate, data_gate_reasons, required_data_fixes = _data_gate_context(
        data_dir, output_dir, final_doc=final_doc, log=log,
    )

    core_perm = str(perms.get("core_etf_permission") or "BLOCKED")
    etf_new_buy = str(policy_permissions.get("etf_new_buy") or "BLOCKED")

    restriction_reasons = decompose_core_etf_restriction(
        execution_scope=str(final_doc.get("execution_scope") or perms.get("execution_scope") or ""),
        core_price_gate_status=str(gates.get("core_price_gate") or "pass"),
        health_gate=str(gates.get("health_gate") or "YELLOW"),
        data_gate=data_gate,
        portfolio_gate=str(gates.get("portfolio_gate") or auth.get("portfolio_gate") or "GREEN"),
        policy_permissions=policy_permissions,
        policy_cap_active=bool(policy_cap.get("active")),
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        actual_buy_allowed=actual_buy,
        core_etf_permission=core_perm,
    )

    candidates = list_etf_underweight_candidates(final_doc)
    weights = _weight_map(output_dir)

    counterfactual = read_output_json(output_dir / "policy_cap_counterfactual.json") or {}
    hypo_etf = int(
        (counterfactual.get("scenarios") or {})
        .get("policy_cap_removed_and_core_etf_unrestricted", {})
        .get("hypothetical_actual_buy_allowed", len(candidates))
    )

    trace_rows: list[dict[str, Any]] = []
    for cand in candidates:
        t = cand["ticker"]
        w = weights.get(t, {})
        gap = float(w.get("gap") or 0)
        target_w = float(w.get("target_weight") or 0)
        current_w = float(w.get("current_weight") or 0)
        asset_group = str(w.get("asset_group") or "")
        is_under = gap > 0.01 or "underweight" in cand["reason"].lower()

        blocked_data = data_gate in {"RED", "YELLOW"}
        blocked_cap = bool(policy_cap.get("active"))
        blocked_perm = core_perm != "ALLOWED" or etf_new_buy != "ALLOWED"
        blocked_actual = actual_buy <= 0

        req_fix_parts: list[str] = []
        if blocked_data:
            req_fix_parts.append("data_gate_GREEN")
        if etf_new_buy == "REVIEW_ONLY":
            req_fix_parts.append("etf_new_buy_ALLOWED")
        if blocked_actual:
            req_fix_parts.append("actual_buy_allowed>0")
        if blocked_cap:
            req_fix_parts.append("policy_cap_review")

        trace_rows.append({
            "ticker": t,
            "name": cand["name"],
            "asset_class": asset_group,
            "target_weight": target_w,
            "current_weight": current_w,
            "gap_weight": round(gap, 2),
            "is_underweight": is_under,
            "candidate_if_unrestricted": True,
            "blocked_by_data_gate": blocked_data,
            "blocked_by_policy_cap": blocked_cap,
            "blocked_by_permission": blocked_perm,
            "blocked_by_actual_buy_allowed": blocked_actual,
            "required_fix": ";".join(req_fix_parts) if req_fix_parts else "none",
            "review_only": core_perm == "RESTRICTED" or etf_new_buy == "REVIEW_ONLY",
            "actual_buy_permission": False,
            "execution_scope_constraint": str(final_doc.get("execution_scope") or ""),
            "allowed_size_pct_actual": cand["allowed_size_pct"],
            "wait_reason": cand["reason"],
        })

    recommended: list[str] = []
    if data_gate == "YELLOW":
        recommended.append(
            f"Primary ETF blocker: data_gate=YELLOW keeps core_etf=RESTRICTED ({len(candidates)} underweight candidates)"
        )
    if etf_new_buy == "REVIEW_ONLY":
        recommended.append("etf_new_buy=REVIEW_ONLY — manual review required even when scope allows ETF rebalance")
    if actual_buy == 0:
        recommended.append("Actual Buy Allowed=0 — no executable ETF buys today regardless of underweight gaps")
    recommended.append(ETF_ONLY_NOTE)
    if hypo_etf > 0 and core_perm != "ALLOWED":
        recommended.append(
            f"Counterfactual: {hypo_etf} ETF candidates if core_etf unrestricted (see policy_cap_counterfactual.json)"
        )

    return {
        "schema_version": "1.0",
        "as_of": final_doc.get("as_of"),
        "run_id": final_doc.get("run_id"),
        "core_etf_permission": core_perm,
        "etf_new_buy_state": etf_new_buy,
        "restriction_reasons": restriction_reasons,
        "data_gate_status": unified_gate,
        "data_gate_reasons": data_gate_reasons,
        "required_data_fixes": required_data_fixes,
        "eligible_etf_underweight_count": len(candidates),
        "hypothetical_etf_buy_count_if_unrestricted": hypo_etf,
        "execution_scope": str(final_doc.get("execution_scope") or ""),
        "execution_scope_note": ETF_ONLY_NOTE,
        "actual_buy_allowed": actual_buy,
        "policy_cap_active": bool(policy_cap.get("active")),
        "policy_cap_regime": policy_cap.get("cap_regime"),
        "dry_run_days": dry_run_days,
        "dry_run_required": dry_run_required,
        "counterfactual_etf_path_open": bool(
            (counterfactual.get("scenarios") or {})
            .get("policy_cap_removed_and_core_etf_unrestricted", {})
            .get("would_open_buy_path")
        ),
        "recommended_fix": recommended,
        "trace_rows": trace_rows,
        "diagnostics_path": DIAGNOSTICS_JSON,
        "trace_csv_path": TRACE_CSV,
    }


def write_core_etf_permission_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_core_etf_permission_diagnostics(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_rows = doc.pop("trace_rows", [])
    json_path = output_dir / "core_etf_permission_diagnostics.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "core_etf_candidate_trace.csv"
    if trace_rows:
        fields = list(trace_rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in trace_rows:
                writer.writerow(row)
    else:
        csv_path.write_text("ticker,name\n", encoding="utf-8-sig")

    # P5-A: blocking duration diagnostic (does not change permission / buy allowed)
    try:
        from src.validation.core_etf_blocking_duration import write_core_etf_blocking_duration

        duration = write_core_etf_blocking_duration(
            output_dir,
            as_of=str(doc.get("as_of") or ""),
            core_etf_diagnostics=doc,
        )
        doc["blocking_duration"] = {
            "streak_days": duration.get("core_etf_restricted_days_current_streak"),
            "dominant_reason": duration.get("dominant_restriction_reason"),
            "eligible_today": duration.get("eligible_etf_underweight_count_today"),
            "artifact": "outputs/core_etf_blocking_duration.json",
        }
        json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    doc["trace_rows"] = trace_rows
    return doc


def format_core_etf_report_lines(doc: dict[str, Any]) -> list[str]:
    rec = doc.get("recommended_fix") or []
    reasons = doc.get("restriction_reasons") or []
    lines = [
        "### Core ETF Permission Diagnostic",
        f"> **{ETF_ONLY_NOTE}**",
        f"- **Core ETF permission**: `{doc.get('core_etf_permission', '—')}` · "
        f"etf_new_buy=`{doc.get('etf_new_buy_state', '—')}`",
        f"- **Eligible ETF underweight if unrestricted**: {doc.get('eligible_etf_underweight_count', 0)} "
        f"(counterfactual hypothetical={doc.get('hypothetical_etf_buy_count_if_unrestricted', 0)})",
        f"- **Actual ETF buy allowed**: {doc.get('actual_buy_allowed', 0)}",
        f"- **data_gate**: `{doc.get('data_gate_status', '—')}`",
        f"- **Main restriction reasons**: {', '.join(reasons[:4]) or '—'}",
        f"- **Required fix**: {rec[0] if rec else '—'}",
        f"- **Detail**: `{DIAGNOSTICS_JSON}` · `{TRACE_CSV}`",
    ]
    bd = doc.get("blocking_duration")
    if isinstance(bd, dict):
        lines.append(
            f"- **Core ETF 잠김 지속**: {bd.get('streak_days', '—')}일 연속 "
            f"(주 원인: `{bd.get('dominant_reason', '—')}`) · "
            f"즉시 집행 가능 후보 {bd.get('eligible_today', doc.get('eligible_etf_underweight_count', 0))}건"
        )
    else:
        pass
    lines.append("")
    return lines


def core_etf_summary_for_no_action(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "core_etf_permission": doc.get("core_etf_permission"),
        "eligible_etf_underweight_count": doc.get("eligible_etf_underweight_count"),
        "hypothetical_etf_buy_count_if_unrestricted": doc.get("hypothetical_etf_buy_count_if_unrestricted"),
        "data_gate_status": doc.get("data_gate_status"),
        "restriction_reasons": doc.get("restriction_reasons"),
        "counterfactual_etf_path_open": doc.get("counterfactual_etf_path_open"),
        "core_etf_diagnostics_path": DIAGNOSTICS_JSON,
    }
