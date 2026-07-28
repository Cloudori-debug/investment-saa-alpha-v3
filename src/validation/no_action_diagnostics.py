"""No-action root-cause diagnostics — outputs/no_action_diagnostics.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.execution_scope import count_dry_run_days
from src.report.authoritative_status import resolve_authoritative_execution
from src.report.execution_metrics import count_executable_actions, list_buy_candidates
from src.report.io_utils import read_output_json
from src.validation.fail_soft_pipeline import _sector_coverage_from_gpt
def _acceptance_item_detail(acceptance: dict[str, Any], ac_id: str) -> dict[str, Any]:
    for item in acceptance.get("items") or []:
        if isinstance(item, dict) and item.get("id") == ac_id:
            detail = item.get("detail")
            return detail if isinstance(detail, dict) else {}
    return {}


def _acceptance_item_gate(acceptance: dict[str, Any], ac_id: str, name: str) -> str:
    for item in acceptance.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == ac_id or item.get("name") == name:
            msg = str(item.get("message") or "")
            if "gate=" in msg:
                return msg.split("gate=", 1)[-1].strip()
            detail = item.get("detail") or {}
            if isinstance(detail, dict) and detail.get("gate"):
                return str(detail["gate"])
    return ""


def _gate_detail_complete(acceptance: dict[str, Any]) -> bool:
    for ac_id in ("AC-02", "AC-03"):
        detail = _acceptance_item_detail(acceptance, ac_id)
        gate = _acceptance_item_gate(acceptance, ac_id, "")
        if gate == "RED" and not detail:
            return False
        if gate == "RED" and not detail.get("fail_reasons"):
            return False
    return True


def _status_alignment(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    brief = read_output_json(output_dir / "daily_brief.json") or {}
    v2 = read_output_json(output_dir / "alpha_v2_summary.json") or {}
    auth = resolve_authoritative_execution(data_dir, output_dir)

    acc_scope = str(acceptance.get("execution_scope") or "")
    brief_scope = str((brief.get("system_status") or {}).get("execution_scope") or "")
    exec_b_scope = str((brief.get("execution") or {}).get("execution_scope") or "")
    v2_scope = str((v2.get("execution_context") or {}).get("execution_scope") or "")
    auth_scope = str(auth.get("execution_scope") or "")

    mismatches: list[str] = []
    for label, scope in [
        ("acceptance", acc_scope),
        ("daily_brief.system_status", brief_scope),
        ("daily_brief.execution", exec_b_scope),
        ("alpha_v2_summary", v2_scope),
    ]:
        if scope and auth_scope and scope != auth_scope:
            mismatches.append(f"{label}={scope} != authoritative={auth_scope}")

    report_path = output_dir / "daily_report.md"
    report_scope_hint = None
    if report_path.exists():
        head = report_path.read_text(encoding="utf-8").split("\n## 1.")[0]
        if auth_scope == "NO_TRADE" and "NO_TRADE" not in head and "ETF_ONLY" in head:
            mismatches.append("daily_report top shows ETF_ONLY while authoritative NO_TRADE")
            report_scope_hint = "ETF_ONLY_stale"

    return {
        "pass": len(mismatches) == 0,
        "authoritative_execution_scope": auth_scope,
        "scopes": {
            "acceptance": acc_scope,
            "daily_brief_system_status": brief_scope,
            "daily_brief_execution": exec_b_scope,
            "alpha_v2_summary": v2_scope,
            "authoritative": auth_scope,
        },
        "mismatches": mismatches,
        "report_scope_hint": report_scope_hint,
    }


def _run_counterfactual(
    *,
    data_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    from src.validation.policy_cap_counterfactual import build_counterfactual_results_for_no_action

    return build_counterfactual_results_for_no_action(data_dir, output_dir)


def _legacy_counterfactual_compat(cf: dict[str, Any]) -> dict[str, Any]:
    """Map new scenario keys for older tests/scripts."""
    if "policy_cap_removed" in cf:
        return cf
    out = dict(cf)
    removed = cf.get("policy_cap_removed_only") or {}
    if removed:
        out["policy_cap_removed"] = {
            "label": "policy_cap_removed",
            "would_open_buy_path": removed.get("would_open_buy_path"),
            "main_block_reason": removed.get("first_remaining_blocker"),
            "execution_scope": removed.get("execution_scope"),
            "core_etf_permission": removed.get("core_etf_permission"),
            "alpha_auto_buy_permission": removed.get("alpha_auto_buy_permission"),
        }
    all_soft = cf.get("all_soft_blockers_cleared") or {}
    if all_soft:
        out["data_gate_green_assumed"] = {
            "label": "data_gate_green_assumed",
            "would_open_buy_path": all_soft.get("would_open_buy_path"),
            "main_block_reason": all_soft.get("first_remaining_blocker"),
            "execution_scope": all_soft.get("execution_scope"),
            "core_etf_permission": all_soft.get("core_etf_permission"),
            "alpha_auto_buy_permission": all_soft.get("alpha_auto_buy_permission"),
        }
    actual = cf.get("actual_state") or {}
    cov_pct = float((actual.get("shortlist_eligible_count") or 0))
    out["sector_coverage_80_assumed"] = {
        "label": "sector_coverage_80_assumed",
        "would_open_buy_path": bool(cov_pct),
        "main_block_reason": "sector_coverage_assumed_ok",
    }
    return out


def _collect_blockers(
    *,
    auth: dict[str, Any],
    final_doc: dict[str, Any],
    perms: dict[str, Any],
    metrics: dict[str, Any],
    acceptance: dict[str, Any],
    log: dict[str, Any],
) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    secondary: list[str] = []

    if metrics["actual_buy_allowed_count"] == 0:
        primary.append("Actual Buy Allowed=0")

    for gate_label, gate_val in [
        ("unified_data_gate", auth.get("unified_data_gate")),
        ("portfolio_gate", auth.get("portfolio_gate")),
    ]:
        if str(gate_val or "").upper() == "RED":
            primary.append(f"{gate_label}=RED")

    if str(auth.get("execution_scope") or "") == "NO_TRADE":
        primary.append("execution_scope=NO_TRADE")

    if str(auth.get("full_status") or "").upper() == "RED":
        primary.append("full_status=RED")

    policy_cap = final_doc.get("policy_cap") or {}
    if policy_cap.get("active"):
        secondary.append(f"policy_cap={policy_cap.get('cap_regime', 'active')}")

    main_block = perms.get("main_block_reason")
    if main_block and main_block not in primary:
        secondary.append(str(main_block))

    for ac_id in ("AC-02", "AC-03"):
        detail = _acceptance_item_detail(acceptance, ac_id)
        for reason in detail.get("fail_reasons") or []:
            tag = f"{ac_id}:{reason}"
            if tag not in primary and tag not in secondary:
                secondary.append(tag)

    if log.get("health_gate") == "YELLOW":
        secondary.append("health_gate=YELLOW")

    cov = perms.get("sector_coverage") or {}
    top10 = float(cov.get("top10_sector_coverage_pct") or 100)
    if top10 < 80:
        secondary.append(f"top10_sector_coverage={top10}%")

    core_perm = perms.get("core_etf_permission")
    if core_perm in {"BLOCKED", "RESTRICTED"}:
        secondary.append(f"core_etf_permission={core_perm}")

    alpha_perm = perms.get("alpha_auto_buy_permission")
    if alpha_perm == "BLOCKED":
        secondary.append("alpha_auto_buy_permission=BLOCKED")

    return primary, secondary


def _recommended_fix(
    *,
    primary: list[str],
    secondary: list[str],
    alignment: dict[str, Any],
    gate_complete: bool,
    counterfactual: dict[str, Any],
) -> list[str]:
    fixes: list[str] = []
    if not alignment.get("pass"):
        fixes.append("Align acceptance, daily_brief, daily_report, alpha_v2_summary to authoritative execution_scope")
    if not gate_complete:
        fixes.append("Populate AC-02/AC-03 gate detail fail_reasons when gate=RED")
    if any("unified_data_gate=RED" in p for p in primary):
        fixes.append("Resolve unified data gate drivers (health/portfolio/alpha merge) before expecting buys")
    if any("portfolio_gate=RED" in p for p in primary):
        fixes.append("Review regime and input validation driving portfolio_gate=RED")
    if (
        counterfactual.get("policy_cap_removed_only", {}).get("would_open_buy_path") is False
        and counterfactual.get("policy_cap_removed_and_core_etf_unrestricted", {}).get("would_open_buy_path")
    ):
        fixes.append(
            "Policy cap is not the primary ETF blocker — data_gate YELLOW / etf REVIEW_ONLY likely dominate"
        )
    elif counterfactual.get("policy_cap_removed_only", {}).get("would_open_buy_path"):
        fixes.append("Policy cap may be limiting scope — verify cap expiry and manual review")
    shortlist = (counterfactual.get("actual_state") or {}).get("shortlist_eligible_count", 0)
    if shortlist == 0:
        fixes.append(
            "Shortlist pool empty despite B-grade — see outputs/alpha_shortlist_summary.json (pillar pass gaps)"
        )
    cf_rec = counterfactual.get("recommended_next_action") or []
    for item in cf_rec[:2]:
        if item not in fixes:
            fixes.append(item)
    if not fixes and primary:
        fixes.append("No-action appears policy-intended; monitor gates and dry-run progress")
    return fixes


def build_no_action_diagnostics(
    data_dir: Path,
    output_dir: Path,
    *,
    clarity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    log_path = output_dir / "decision_log.jsonl"
    log: dict[str, Any] = {}
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            log = json.loads(lines[-1])

    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc, acceptance_doc=acceptance)
    metrics = count_executable_actions(final_doc)
    perms = final_doc.get("execution_permissions") or {}
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    policy_cap = final_doc.get("policy_cap") or {}

    dry_run_days = count_dry_run_days(output_dir)
    dry_run_required = 10
    shadow = read_output_json(output_dir / "shadow_diagnostic.json") or {}
    dry_run_required = int((shadow.get("gates") or {}).get("dry_run_required") or dry_run_required)

    alignment = _status_alignment(data_dir, output_dir)
    gate_complete = _gate_detail_complete(acceptance)

    primary, secondary = _collect_blockers(
        auth=auth,
        final_doc=final_doc,
        perms=perms,
        metrics=metrics,
        acceptance=acceptance,
        log=log,
    )

    health_doc = read_output_json(output_dir / "system_health.json") or {}
    critical_fail = any(
        c.get("status") == "fail" and c.get("name") in {
            "target_weights", "positions", "load", "prices_coverage",
            "core_price_gate", "target_portfolio_guard",
        }
        for c in health_doc.get("checks") or []
        if isinstance(c, dict)
    )

    actual_buy = metrics["actual_buy_allowed_count"]
    no_action_expected = bool(
        actual_buy == 0
        and not critical_fail
        and final_doc
        and (len(primary) > 0 or len(secondary) > 0)
    )

    counterfactual_raw = _run_counterfactual(data_dir=data_dir, output_dir=output_dir)
    counterfactual = _legacy_counterfactual_compat(counterfactual_raw)

    buy_candidates = list_buy_candidates(final_doc)
    risk_trims = metrics.get("risk_reduce_trims") or []

    actual_buy_trace = {
        "input_execution_scope": str(final_doc.get("execution_scope") or log.get("execution_scope") or ""),
        "authoritative_execution_scope": auth.get("execution_scope"),
        "data_gate": final_doc.get("data_gate") or log.get("data_gate"),
        "unified_data_gate": auth.get("unified_data_gate"),
        "portfolio_gate": auth.get("portfolio_gate"),
        "policy_cap_active": bool(policy_cap.get("active")),
        "market_status": auth.get("market_status"),
        "operational_status": auth.get("operational_status"),
        "executable_action_count": metrics["executable_action_count"],
        "buy_candidate_count": len(buy_candidates),
        "risk_reduce_candidate_count": len(risk_trims),
        "final_actual_buy_allowed": actual_buy,
        "dry_run_days": dry_run_days,
        "dry_run_required": dry_run_required,
    }
    v2 = read_output_json(output_dir / "alpha_v2_summary.json") or {}
    actual_buy_trace["candidate_count"] = len(v2.get("final_candidates") or [])

    clarity_pass = clarity.get("pass") if clarity else None
    if clarity_pass is False and alignment.get("pass"):
        alignment = {**alignment, "pass": False, "mismatches": alignment.get("mismatches", []) + ["report_clarity_validation failed"]}

    from src.validation.alpha_gate_diagnostics import (
        alpha_gate_summary_for_no_action,
        build_alpha_gate_diagnostics,
    )
    from src.validation.alpha_shortlist_diagnostics import (
        shortlist_summary_for_no_action,
        SUMMARY_JSON,
    )
    from src.validation.core_etf_permission_diagnostics import core_etf_summary_for_no_action
    from src.validation.data_gate_diagnostics import (
        build_data_gate_diagnostics,
        data_gate_summary_for_no_action,
        data_gate_tags_for_no_action,
    )

    alpha_diag = build_alpha_gate_diagnostics(data_dir, output_dir)
    data_gate_doc = read_output_json(output_dir / "data_gate_diagnostics.json") or {}
    if not data_gate_doc:
        data_gate_doc = build_data_gate_diagnostics(data_dir, output_dir)
    shortlist_summary = read_output_json(output_dir / "alpha_shortlist_summary.json") or {}
    core_etf_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    if not core_etf_doc:
        from src.validation.core_etf_permission_diagnostics import build_core_etf_permission_diagnostics

        core_etf_doc = build_core_etf_permission_diagnostics(data_dir, output_dir)
    for tag in alpha_gate_summary_for_no_action(alpha_diag):
        if tag not in secondary and tag not in primary:
            secondary.append(tag)
    for tag in data_gate_tags_for_no_action(data_gate_doc):
        if tag not in secondary and tag not in primary:
            secondary.append(tag)

    from src.validation.pmi_kr_manual_verified_reevaluation import (
        reevaluation_summary_for_no_action,
    )

    pmi_reeval_doc = read_output_json(output_dir / "pmi_kr_manual_verified_reevaluation.json") or {}

    recommended_fix = _recommended_fix(
        primary=primary,
        secondary=secondary,
        alignment=alignment,
        gate_complete=gate_complete,
        counterfactual=counterfactual,
    )
    dg_fixes = data_gate_doc.get("recommended_fix") or []
    for item in dg_fixes[:2]:
        if item not in recommended_fix:
            recommended_fix.insert(0, item)

    return {
        "schema_version": "1.0",
        "as_of": final_doc.get("as_of") or acceptance.get("as_of") or log.get("as_of"),
        "run_id": final_doc.get("run_id") or acceptance.get("run_id") or log.get("run_id"),
        "no_action_is_expected": no_action_expected,
        "primary_blockers": primary,
        "secondary_blockers": secondary,
        "alpha_gate_diagnostics_path": "outputs/alpha_gate_diagnostics.json",
        "alpha_gate_summary": alpha_diag.get("alpha_gate_reason_summary"),
        "alpha_shortlist_summary_path": SUMMARY_JSON,
        "shortlist_pool_diagnostic": shortlist_summary_for_no_action(shortlist_summary) if shortlist_summary else {},
        "core_etf_diagnostics_path": "outputs/core_etf_permission_diagnostics.json",
        "core_etf_permission_diagnostic": core_etf_summary_for_no_action(core_etf_doc) if core_etf_doc else {},
        "data_gate_diagnostics_path": "outputs/data_gate_diagnostics.json",
        "data_gate_diagnostic": data_gate_summary_for_no_action(data_gate_doc) if data_gate_doc else {},
        "pmi_kr_manual_verified_reevaluation_path": "outputs/pmi_kr_manual_verified_reevaluation.json",
        "pmi_kr_manual_verified_reevaluation": reevaluation_summary_for_no_action(pmi_reeval_doc)
        if pmi_reeval_doc
        else {},
        "status_alignment_pass": alignment.get("pass", False),
        "status_alignment": alignment,
        "gate_detail_complete": gate_complete,
        "counterfactual_results": counterfactual,
        "policy_cap_counterfactual_path": "outputs/policy_cap_counterfactual.json",
        "actual_buy_trace": actual_buy_trace,
        "recommended_fix": recommended_fix,
        "report_clarity_pass": clarity_pass,
        "system_error_likely": critical_fail or not final_doc,
    }


def write_no_action_diagnostics(
    data_dir: Path,
    output_dir: Path,
    *,
    clarity: dict[str, Any] | None = None,
    light: bool = False,
) -> dict[str, Any]:
    if not light:
        from src.validation.policy_cap_counterfactual import write_policy_cap_counterfactual
        from src.validation.core_etf_permission_diagnostics import write_core_etf_permission_diagnostics
        from src.validation.data_gate_diagnostics import write_data_gate_diagnostics

        write_policy_cap_counterfactual(data_dir, output_dir)
        from src.validation.kosis_tier2_refresh_diagnostics import run_kosis_tier2_refresh_with_diagnostics
        from src.validation.market_indicator_schema_diagnostics import write_market_indicator_schema_diagnostics

        run_kosis_tier2_refresh_with_diagnostics(data_dir, output_dir)
        write_market_indicator_schema_diagnostics(data_dir, output_dir)
        write_core_etf_permission_diagnostics(data_dir, output_dir)
        write_data_gate_diagnostics(data_dir, output_dir)
    doc = build_no_action_diagnostics(data_dir, output_dir, clarity=clarity)
    path = output_dir / "no_action_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc
