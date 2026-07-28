"""Alpha gate YELLOW root-cause diagnostics — outputs/alpha_gate_diagnostics.json."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json

TIER2_STALE_WARN_DAYS = 45
TIER2_SOURCE_FILE = "data/tier2_provenance.json"
DIAGNOSTICS_PATH = "outputs/alpha_gate_diagnostics.json"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _health_check(health: dict[str, Any], name: str) -> dict[str, Any]:
    for chk in health.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == name:
            return chk
    return {}


def _tier2_stale_fields(data_dir: Path) -> tuple[str, list[dict[str, Any]]]:
    prov_path = data_dir / "tier2_provenance.json"
    if not prov_path.exists():
        return "MISSING", []
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "PARSE_ERROR", []

    fields = prov.get("fields") or {}
    stale_rows: list[dict[str, Any]] = []
    for name, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        status = str(meta.get("status") or "")
        threshold = int(meta.get("threshold_days") or TIER2_STALE_WARN_DAYS)
        stale_days = int(meta.get("stale_business_days") or 0)
        is_stale = (
            status in {"stale", "manual_required"}
            or (status != "fresh" and stale_days > threshold)
        )
        if not is_stale:
            continue
        action = "refresh_api_source"
        if meta.get("fallback_used") or str(meta.get("fetch_status") or "") == "failed":
            action = "fix_api_or_manual_override"
        if str(meta.get("status") or "") == "manual_required":
            action = "manual_provenance_update_required"
        stale_rows.append({
            "stale_field": name,
            "last_updated": str(meta.get("value_date") or meta.get("last_updated") or ""),
            "stale_reference_date": str(meta.get("stale_reference_date") or ""),
            "stale_days": stale_days,
            "threshold_days": threshold,
            "status": status or ("stale" if stale_days > threshold else "warn"),
            "source_file": TIER2_SOURCE_FILE,
            "source": str(meta.get("source") or ""),
            "fetch_method": str(meta.get("fetch_method") or ""),
            "fallback_used": bool(meta.get("fallback_used")),
            "required_action": action,
        })
    stale_rows.sort(key=lambda r: r["stale_days"], reverse=True)

    if not fields:
        return "EMPTY", stale_rows
    if any(r["status"] in {"stale", "manual_required"} or r["stale_days"] > r["threshold_days"] for r in stale_rows):
        return "STALE", stale_rows
    if stale_rows:
        return "WARN", stale_rows
    return "PASS", stale_rows


def _count_grades(output_dir: Path) -> dict[str, int]:
    rows = _read_csv_rows(output_dir / "alpha_scored_universe.csv")
    counts: dict[str, int] = {}
    for row in rows:
        g = str(row.get("grade") or "")
        counts[g] = counts.get(g, 0) + 1
    return counts


def _buy_ready_count(output_dir: Path) -> int:
    rows = _read_csv_rows(output_dir / "alpha_signal_board.csv")
    return sum(1 for r in rows if str(r.get("action_state") or "") == "Buy-ready")


def _classify_gpt_context_zero(
    *,
    gpt_count: int,
    csv_candidate_count: int,
    shortlist_count: int,
    signal_board_count: int,
    b_grade_count: int,
    alpha_gate: str,
    execution_scope: str,
    alpha_trade_permission: str,
    limitations: list[str],
    excluded_summary: dict[str, Any],
    shortlist_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if gpt_count > 0:
        return {"classification": "candidates_present", "detail": f"gpt_context has {gpt_count} top_candidates"}

    flags: list[str] = []
    if csv_candidate_count > 0:
        return {
            "classification": "export_omission",
            "flags": ["export_omission"],
            "detail": "alpha_candidates.csv has rows but gpt_context.top_candidates is empty",
        }
    if shortlist_count == 0 and csv_candidate_count == 0:
        if b_grade_count > 0:
            flags.append("selection_pool_empty_despite_b_grade")
        else:
            flags.append("actual_zero_candidates")
    if signal_board_count > 0 and gpt_count == 0 and csv_candidate_count == 0:
        flags.append("signal_board_holdings_only")
    if int(excluded_summary.get("stale_data") or 0) > 0 or "stale" in " ".join(limitations).lower():
        flags.append("stale_data_contributor")
    if alpha_gate in {"RED", "YELLOW"}:
        flags.append("gate_yellow_or_red")
    if execution_scope in {"NO_TRADE", "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"}:
        flags.append("scope_restricted")
    if alpha_trade_permission in {"BLOCK_NEW_BUY", "BLOCK_ALL"}:
        flags.append("permission_blocked")

    if not flags:
        flags.append("unknown")

    primary = flags[0]
    if primary == "export_omission":
        detail = "alpha_candidates.csv has rows but gpt_context.top_candidates is empty"
    elif primary == "selection_pool_empty_despite_b_grade":
        top_fails = (shortlist_summary or {}).get("top_fail_reasons") or []
        fail_hint = f" — top fail reasons: {', '.join(top_fails[:3])}" if top_fails else ""
        detail = (
            f"scored universe has {b_grade_count} B-grade rows but shortlist/proposal pool is empty "
            f"(pillar thresholds / min_pillars_pass not met){fail_hint}"
        )
        if shortlist_summary:
            detail += (
                f"; shortlist_eligible={shortlist_summary.get('shortlist_eligible_count', 0)} "
                f"see outputs/alpha_shortlist_summary.json"
            )
    elif primary == "actual_zero_candidates":
        detail = "no qualifying alpha candidates after scoring and selection"
    elif primary == "signal_board_holdings_only":
        detail = "signal_board has holdings-review rows; gpt_context top_candidates empty (no shortlist export)"
    else:
        detail = "; ".join(flags)

    return {"classification": primary, "flags": flags, "detail": detail}


def _pit_and_fundamental_status(gpt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    excluded = gpt.get("excluded_summary") or {}
    limitations = gpt.get("data_limitations") or []
    pit_gate = str(gpt.get("alpha_data_gate") or "—")
    stale_n = int(excluded.get("stale_data") or 0)
    missing_fund = int(excluded.get("missing_fundamentals") or 0)
    pit_notes = [x for x in limitations if "PIT" in x or "재무" in x or "시세" in x]

    pit_status = {
        "gate": pit_gate,
        "stale_excluded_count": stale_n,
        "missing_fundamentals_count": missing_fund,
        "notes": pit_notes[:5],
    }
    fund_status = {
        "excluded_summary": excluded,
        "limitations": limitations[:8],
        "point_in_time_gate": pit_gate,
    }
    return pit_status, fund_status


def build_alpha_gate_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    gpt = read_output_json(output_dir / "gpt_context.json") or {}
    health = read_output_json(output_dir / "system_health.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    log: dict[str, Any] = {}
    log_path = output_dir / "decision_log.jsonl"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            log = json.loads(lines[-1])

    alpha_gate = str(
        log.get("alpha_gate")
        or gpt.get("alpha_data_gate")
        or _acceptance_gate(acceptance, "AC-04")
        or "—"
    )
    unified_gate = str(log.get("data_gate") or gpt.get("data_gate") or "—")

    tier2_status, stale_tier2 = _tier2_stale_fields(data_dir)
    tier2_health = _health_check(health, "tier2_provenance")

    csv_candidates = len(_read_csv_rows(output_dir / "alpha_candidates.csv"))
    shortlist_count = len(_read_csv_rows(output_dir / "alpha_shortlist.csv"))
    signal_board_count = len(_read_csv_rows(output_dir / "alpha_signal_board.csv"))
    gpt_count = len(gpt.get("top_candidates") or [])
    grade_counts = _count_grades(output_dir)
    b_grade_count = int(grade_counts.get("B", 0))
    buy_ready_count = _buy_ready_count(output_dir)

    limitations = list(gpt.get("data_limitations") or [])
    excluded_summary = gpt.get("excluded_summary") or {}
    execution_scope = str(
        gpt.get("execution_scope")
        or acceptance.get("execution_scope")
        or final.get("execution_scope")
        or ""
    )
    alpha_trade_permission = str(gpt.get("alpha_trade_permission") or "")

    shortlist_summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}

    gpt_zero = _classify_gpt_context_zero(
        gpt_count=gpt_count,
        csv_candidate_count=csv_candidates,
        shortlist_count=shortlist_count,
        signal_board_count=signal_board_count,
        b_grade_count=b_grade_count,
        alpha_gate=alpha_gate,
        execution_scope=execution_scope,
        alpha_trade_permission=alpha_trade_permission,
        limitations=limitations,
        excluded_summary=excluded_summary,
        shortlist_summary=shortlist_summary,
    )

    shortlist_meta = gpt.get("shortlist_meta") or {}
    kr_meta = gpt.get("kr_alpha_meta") or {}
    sector_cov = shortlist_meta.get("top10_sector_coverage_pct")
    if sector_cov is None:
        sector_cov = (kr_meta.get("sector_coverage") or {}).get("top10_sector_coverage_pct")
    sector_status = {
        "top10_sector_coverage_pct": sector_cov,
        "alpha_sector_data_gate": shortlist_meta.get("alpha_sector_data_gate") or kr_meta.get("alpha_sector_data_gate"),
        "shortlist_count": shortlist_meta.get("shortlist_count", shortlist_count),
    }

    flow_meta = kr_meta.get("flow_refresh") or {}
    flow_status = {
        "fresh_ratio": flow_meta.get("fresh_ratio"),
        "watched_count": flow_meta.get("watched_count"),
        "pykrx_failed_count": flow_meta.get("pykrx_failed_count"),
        "status": "fresh" if float(flow_meta.get("fresh_ratio") or 0) >= 0.8 else "degraded",
    }

    pit_status, fund_status = _pit_and_fundamental_status(gpt)

    alpha_price = _health_check(health, "alpha_price_gate")
    gpt_health = _health_check(health, "gpt_context")

    primary: list[str] = []
    secondary: list[str] = []

    if alpha_gate == "YELLOW":
        primary.append("alpha_gate=YELLOW")
    elif alpha_gate == "RED":
        primary.append("alpha_gate=RED")

    if tier2_status in {"STALE", "WARN", "MISSING"}:
        secondary.append(f"tier2_provenance={tier2_status}")
    for row in stale_tier2[:3]:
        secondary.append(f"tier2_stale:{row['stale_field']}={row['stale_days']}d")

    if gpt_count == 0:
        secondary.append(f"gpt_context_candidates=0 ({gpt_zero['classification']})")
    if shortlist_count == 0 and b_grade_count > 0:
        secondary.append(f"shortlist_empty_despite_b_grade={b_grade_count}")
    if pit_status.get("gate") == "YELLOW":
        secondary.append("pit_fundamental_gate=YELLOW")
    if alpha_price.get("status") == "warn":
        secondary.append(f"alpha_price_gate={alpha_price.get('message', 'warn')}")
    if execution_scope in {"ETF_ONLY", "NO_TRADE"}:
        secondary.append(f"execution_scope={execution_scope}")
    if alpha_trade_permission in {"BLOCK_NEW_BUY", "BLOCK_ALL"}:
        secondary.append(f"alpha_trade_permission={alpha_trade_permission}")

    reason_parts: list[str] = []
    if tier2_status in {"STALE", "WARN"}:
        reason_parts.append(f"tier2 stale ({len(stale_tier2)} fields)")
    if gpt_count == 0:
        reason_parts.append(gpt_zero["classification"].replace("_", " "))
    if pit_status.get("gate") == "YELLOW":
        reason_parts.append("PIT/fundamental YELLOW")
    if alpha_price.get("status") == "warn":
        reason_parts.append("alpha price coverage warn")
    if not reason_parts:
        reason_parts.append(f"alpha_gate={alpha_gate}")

    recommended: list[str] = []
    if stale_tier2:
        names = ", ".join(r["stale_field"] for r in stale_tier2[:5])
        recommended.append(f"Refresh stale tier2 macro fields ({names}) via tier2 API sync")
    if gpt_zero["classification"] == "selection_pool_empty_despite_b_grade":
        recommended.append("Review alpha selection thresholds — B-grade stocks exist but shortlist pool is empty")
    elif gpt_zero["classification"] == "export_omission":
        recommended.append("Fix gpt_context export — alpha_candidates.csv not reflected in top_candidates")
    elif gpt_count == 0:
        recommended.append("Investigate alpha pipeline selection — no candidates exported to gpt_context")
    if alpha_price.get("status") == "warn":
        recommended.append("Improve alpha top30 price coverage or resolve stale alpha price tickers")
    if not recommended:
        recommended.append("Monitor alpha_gate; no single dominant fix identified")

    v2 = read_output_json(output_dir / "alpha_v2_summary.json") or {}
    v2_candidates = len(v2.get("final_candidates") or [])

    return {
        "schema_version": "1.0",
        "as_of": gpt.get("as_of") or acceptance.get("as_of") or log.get("as_of"),
        "run_id": final.get("run_id") or acceptance.get("run_id") or log.get("run_id"),
        "alpha_gate_status": alpha_gate,
        "unified_data_gate": unified_gate,
        "alpha_gate_reason_summary": " · ".join(reason_parts),
        "primary_alpha_blockers": primary,
        "secondary_alpha_blockers": secondary,
        "tier2_provenance_status": tier2_status,
        "stale_tier2_fields": stale_tier2,
        "tier2_health_message": tier2_health.get("message"),
        "alpha_candidate_count": csv_candidates,
        "shortlist_count": shortlist_count,
        "b_grade_count": b_grade_count,
        "buy_ready_count": buy_ready_count,
        "gpt_context_candidate_count": gpt_count,
        "signal_board_candidate_count": signal_board_count,
        "alpha_v2_final_candidate_count": v2_candidates,
        "gpt_context_zero_classification": gpt_zero,
        "pit_data_status": pit_status,
        "fundamental_data_status": fund_status,
        "sector_coverage_status": sector_status,
        "flow_data_status": flow_status,
        "alpha_price_gate": {
            "status": alpha_price.get("status"),
            "message": alpha_price.get("message"),
            "detail": alpha_price.get("detail") or {},
        },
        "gpt_context_health": {
            "status": gpt_health.get("status"),
            "message": gpt_health.get("message"),
        },
        "execution_scope": execution_scope,
        "alpha_trade_permission": alpha_trade_permission,
        "recommended_fix": recommended,
        "diagnostics_path": DIAGNOSTICS_PATH,
        "alpha_shortlist_summary_path": "outputs/alpha_shortlist_summary.json",
        "shortlist_pool_diagnostic": {
            "shortlist_pool_empty": shortlist_summary.get("shortlist_pool_empty"),
            "b_grade_count": shortlist_summary.get("b_grade_count", b_grade_count),
            "shortlist_eligible_count": shortlist_summary.get("shortlist_eligible_count"),
            "top_fail_reasons": shortlist_summary.get("top_fail_reasons") or [],
            "most_common_fail_reason": shortlist_summary.get("most_common_fail_reason"),
        } if shortlist_summary else {},
    }


def _acceptance_gate(acceptance: dict[str, Any], ac_id: str) -> str:
    for item in acceptance.get("items") or []:
        if not isinstance(item, dict) or item.get("id") != ac_id:
            continue
        msg = str(item.get("message") or "")
        if "gate=" in msg:
            return msg.split("gate=", 1)[-1].strip()
        detail = item.get("detail") or {}
        if isinstance(detail, dict) and detail.get("gate"):
            return str(detail["gate"])
    return ""


def build_ac04_alpha_gate_detail(
    gate: str,
    *,
    data_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    diag = build_alpha_gate_diagnostics(data_dir, output_dir)
    return {
        "gate": gate,
        "fail_reasons": diag.get("primary_alpha_blockers", []) + diag.get("secondary_alpha_blockers", []),
        "alpha_gate_reason_summary": diag.get("alpha_gate_reason_summary"),
        "tier2_provenance_status": diag.get("tier2_provenance_status"),
        "stale_tier2_fields": diag.get("stale_tier2_fields"),
        "gpt_context_zero_classification": diag.get("gpt_context_zero_classification"),
        "gpt_context_candidate_count": diag.get("gpt_context_candidate_count"),
        "alpha_candidate_count": diag.get("alpha_candidate_count"),
        "b_grade_count": diag.get("b_grade_count"),
        "buy_ready_count": diag.get("buy_ready_count"),
        "pit_data_status": diag.get("pit_data_status"),
        "recommended_fix": diag.get("recommended_fix"),
        "diagnostics_path": DIAGNOSTICS_PATH,
        "blocking": gate == "RED",
    }


def write_alpha_gate_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_alpha_gate_diagnostics(data_dir, output_dir)
    path = output_dir / "alpha_gate_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def alpha_gate_summary_for_no_action(diag: dict[str, Any]) -> list[str]:
    """Short tags for no_action_diagnostics secondary blockers."""
    tags: list[str] = []
    status = str(diag.get("alpha_gate_status") or "")
    if status:
        tags.append(f"alpha_gate={status}")
    summary = str(diag.get("alpha_gate_reason_summary") or "")
    if summary and len(summary) < 80:
        tags.append(f"alpha_gate_reason:{summary}")
    gpt_zero = diag.get("gpt_context_zero_classification") or {}
    if int(diag.get("gpt_context_candidate_count") or 0) == 0:
        tags.append(f"gpt_context_zero:{gpt_zero.get('classification', 'unknown')}")
    if diag.get("tier2_provenance_status") in {"STALE", "WARN", "MISSING"}:
        tags.append(f"tier2={diag.get('tier2_provenance_status')}")
    tags.append(f"see:{DIAGNOSTICS_PATH}")
    return tags


def format_alpha_gate_report_lines(diag: dict[str, Any]) -> list[str]:
    gpt_zero = diag.get("gpt_context_zero_classification") or {}
    fixes = diag.get("recommended_fix") or []
    return [
        "### Alpha Gate Diagnostic",
        f"- **Alpha gate**: `{diag.get('alpha_gate_status', '—')}`",
        f"- **Main reason**: {diag.get('alpha_gate_reason_summary', '—')}",
        f"- **Buy-ready count**: {diag.get('buy_ready_count', 0)}",
        f"- **GPT context candidate count**: {diag.get('gpt_context_candidate_count', 0)} "
        f"({gpt_zero.get('classification', '—')})",
        f"- **B-grade scored count**: {diag.get('b_grade_count', 0)} · "
        f"shortlist {diag.get('shortlist_count', 0)} · "
        f"alpha_candidates.csv {diag.get('alpha_candidate_count', 0)}",
        f"- **Tier2 provenance**: `{diag.get('tier2_provenance_status', '—')}` "
        f"({len(diag.get('stale_tier2_fields') or [])} stale fields)",
        f"- **Required fix**: {fixes[0] if fixes else '—'}",
        f"- **Detail**: `{DIAGNOSTICS_PATH}`",
        "",
    ]


def format_alpha_shortlist_report_lines_from_output(output_dir: Path) -> list[str]:
    from src.validation.alpha_shortlist_diagnostics import (
        format_alpha_shortlist_report_lines,
    )

    summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
    if not summary:
        return []
    return format_alpha_shortlist_report_lines(summary)
