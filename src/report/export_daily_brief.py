from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json
from src.report.display_format import (
    fmt_pct,
    fmt_pct_with_suffix,
    fmt_rate_pct_display,
    shadow_opportunity_action_label,
)
from src.report.execution_metrics import count_executable_actions, list_execution_candidates
from src.exposure.core_saa_reference import CORE_REFERENCE_DISCLAIMER
from src.exposure.absolute_return_policy import CORE_SAA_MANDATE_DISCLAIMER, write_absolute_return_status
from src.timing.asset_accumulation_timing import AR2_DISCLAIMER
from src.alpha.early_alpha_engine import EARLY_ALPHA_DISCLAIMER
from src.alpha.opportunity_engine import OPPORTUNITY_DISCLAIMER
from src.alpha.performance_dashboard import ALPHA_DASHBOARD_DISCLAIMER
from src.hakedaka_gate import (
    ACCOUNTS_DEBUG_DISCLAIMER,
    CALIBRATION_DISCLAIMER,
    CATALYST_EVIDENCE_DISCLAIMER,
    COVERAGE_AUDIT_DISCLAIMER,
    DATA_QUALITY_DISCLAIMER,
    EVIDENCE_DISCLAIMER,
    FORWARD_RETURN_DISCLAIMER,
    FORWARD_RETURN_QA_DISCLAIMER,
    HAKEDAKA_STATUS_DISCLAIMER,
    MANUAL_VERIFICATION_DISCLAIMER,
    NAV_TREASURY_DISCLAIMER,
    RERATING_DISCLAIMER,
    write_latest_hakedaka_status,
)
from src.exposure.shadow_cash_floor_ladder import (
    SHADOW_LADDER_DISCLAIMER,
    write_shadow_cash_floor_ladder_status,
)

REPORT_VERSION = "v2.0"
EXECUTION_AUTHORITY = "v1.0.2"


def _top_alpha_candidates(output_dir: Path, limit: int = 5) -> list[dict[str, Any]]:
    path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "ticker": row.get("ticker", ""),
                "name": row.get("name", ""),
                "grade": row.get("grade", ""),
                "total_score": row.get("total_score", ""),
                "eligible_action": row.get("eligible_action", ""),
            })
    return rows[:limit]


def _top_actions(final: dict[str, Any] | None, limit: int = 8) -> list[dict[str, Any]]:
    if not final:
        return []
    out: list[dict[str, Any]] = []
    for act in final.get("allowed_actions") or []:
        if not isinstance(act, dict):
            continue
        out.append({
            "ticker": act.get("ticker", ""),
            "name": act.get("name", ""),
            "action": act.get("action", ""),
            "allowed_size_pct": act.get("allowed_size_pct", 0),
            "reason": str(act.get("reason", ""))[:120],
        })
    return out[:limit]


def _allocation_summary(compass: dict[str, Any] | None, limit: int = 7) -> list[dict[str, Any]]:
    if not compass:
        return []
    groups = (compass.get("allocation") or {}).get("groups") or []
    summary: list[dict[str, Any]] = []
    for g in groups[:limit]:
        if not isinstance(g, dict):
            continue
        saa = float(g.get("saa_weight") or 0)
        final = float(g.get("final_target") or g.get("effective_weight") or 0)
        summary.append({
            "asset_group": g.get("asset_group", ""),
            "saa_pct": round(saa, 2),
            "final_pct": round(final, 2),
            "taa_delta_ppt": round(final - saa, 2),
        })
    return summary


def _top_group_gaps(final: dict[str, Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    if not final:
        return []
    gaps = ((final.get("operating") or {}).get("group_gaps")) or []
    ranked = sorted(
        [g for g in gaps if isinstance(g, dict)],
        key=lambda x: abs(float(x.get("gap") or 0)),
        reverse=True,
    )
    return [
        {
            "asset_group": g.get("asset_group", ""),
            "current_pct": g.get("current"),
            "target_pct": g.get("target"),
            "gap_ppt": g.get("gap"),
            "action": g.get("action", ""),
        }
        for g in ranked[:limit]
    ]


def _acceptance_items(acceptance: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not acceptance:
        return [], []
    fails: list[str] = []
    warns: list[str] = []
    for item in acceptance.get("items") or []:
        if not isinstance(item, dict):
            continue
        label = f"{item.get('id', '')}:{item.get('name', '')}"
        status = str(item.get("status", "")).lower()
        if status == "fail":
            fails.append(label)
        elif status == "warn":
            warns.append(label)
    return fails, warns


def _alpha_v02_holdings(alpha_v02: dict[str, Any] | None, limit: int = 12) -> list[dict[str, Any]]:
    if not alpha_v02:
        return []
    held = [r for r in (alpha_v02.get("rows") or []) if r.get("in_portfolio")]
    held.sort(key=lambda r: -float(r.get("current_weight_pct") or 0))
    return [
        {
            "ticker": r.get("ticker", ""),
            "name": r.get("name", ""),
            "weight_pct": r.get("current_weight_pct", 0),
            "classification": r.get("classification", ""),
            "new_buy_status": r.get("new_buy_status", ""),
            "reason": str(r.get("reason", ""))[:80],
        }
        for r in held[:limit]
    ]


def _kr_alpha_portfolio_weight(
    final: dict[str, Any] | None,
    exposure: dict[str, Any] | None,
) -> float | None:
    """v1.0.2 authoritative — 전체 포트폴리오 NAV 대비 kr_alpha."""
    if final:
        for g in ((final.get("operating") or {}).get("group_gaps") or []):
            if isinstance(g, dict) and g.get("asset_group") == "kr_alpha":
                cur = g.get("current")
                if cur is not None:
                    return round(float(cur), 2)
    if exposure:
        current = (exposure.get("group_weights") or {}).get("current") or {}
        if "kr_alpha" in current:
            return round(float(current["kr_alpha"]), 2)
    return None


def export_daily_brief(
    output_dir: Path,
    *,
    as_of: str | None = None,
    run_id: str | None = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """GPT Report v2.0 입력용 경량 요약 — v1.0.2 실행 로직 변경 없음."""
    resolved_data = data_dir or (output_dir.parent / "data")
    final = read_output_json(output_dir / "final_execution_decision.json")
    acceptance = read_output_json(output_dir / "acceptance_report.json")
    compass = read_output_json(output_dir / "compass_regime.json")
    shadow = read_output_json(output_dir / "shadow_diagnostic.json")
    alpha_v2 = read_output_json(output_dir / "alpha_v2_summary.json")
    core_ref = read_output_json(output_dir / "core_saa_reference_diagnostic.json")
    alpha_perf = read_output_json(output_dir / "alpha_performance_dashboard.json")
    hakedaka_rerating = read_output_json(output_dir / "hakedaka_rerating_shadow.json")
    hakedaka_quality = read_output_json(output_dir / "hakedaka_data_quality_report.json")
    hakedaka_fin_enrich = read_output_json(output_dir / "hakedaka_financial_enrich_report.json")
    hakedaka_evidence = read_output_json(output_dir / "hakedaka_top10_evidence_pack.json")
    hakedaka_coverage = read_output_json(output_dir / "hakedaka_coverage_audit.json")
    dart_accounts_debug = read_output_json(output_dir / "dart_accounts_debug_summary.json")
    hakedaka_phase4f = read_output_json(output_dir / "hakedaka_phase4f_report.json")
    hakedaka_phase4g = read_output_json(output_dir / "hakedaka_phase4g_report.json")
    hakedaka_phase4h = read_output_json(output_dir / "hakedaka_phase4h_report.json")
    hakedaka_phase4h1 = read_output_json(output_dir / "hakedaka_phase4h1_report.json")
    hakedaka_phase4i = read_output_json(output_dir / "hakedaka_phase4i_report.json")
    hakedaka_phase4i1 = read_output_json(output_dir / "hakedaka_phase4i1_report.json")
    exposure = read_output_json(output_dir / "exposure_lookthrough.json")
    triggers = read_output_json(output_dir / "trigger_reviews.json")
    health = read_output_json(output_dir / "system_health.json")

    latest_hakedaka = write_latest_hakedaka_status(output_dir)
    shadow_ladder = write_shadow_cash_floor_ladder_status(
        output_dir, data_dir=resolved_data,
    )
    absolute_return = write_absolute_return_status(resolved_data, output_dir)
    core_throttle = read_output_json(output_dir / "core_deployment_throttle_status.json") or {}
    ar1_parity = read_output_json(output_dir / "ar1_parity_check.json") or {}
    ar2_timing = read_output_json(output_dir / "ar2_accumulation_timing_report.json") or {}
    early_alpha = read_output_json(output_dir / "early_alpha_decision.json") or {}
    opportunity = read_output_json(output_dir / "opportunity_decision.json") or {}
    opp_analytics = read_output_json(output_dir / "opportunity_analytics.json") or {}

    date = as_of or (final or {}).get("as_of") or (compass or {}).get("as_of") or ""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if final and final.get("generated_at"):
        generated_at = str(final["generated_at"]).replace(" UTC", "Z").replace(" ", "T")
        if not generated_at.endswith("Z"):
            generated_at = f"{generated_at}Z"

    tech = (final or {}).get("technical_status") or {}
    cap = (final or {}).get("policy_cap") or {}
    from src.report.authoritative_status import build_authoritative_status_snapshot

    auth = build_authoritative_status_snapshot(
        resolved_data,
        output_dir,
        final_doc=final,
        acceptance_doc=acceptance,
    )
    shadow_exec = (shadow or {}).get("execution") or {}
    shadow_signals = (shadow or {}).get("signals") or {}
    shadow_amounts = (shadow or {}).get("amounts") or {}
    shadow_perf = (shadow or {}).get("performance") or {}
    shadow_obs = (shadow or {}).get("observations") or {}
    duration = (shadow or {}).get("duration_bond_status") or {}
    gates = (shadow or {}).get("gates") or {}

    core_gate = "pass"
    if health:
        for chk in health.get("checks") or []:
            if isinstance(chk, dict) and chk.get("name") == "core_price_gate":
                core_gate = str(chk.get("status", "pass"))
                break

    fail_items, warn_items = _acceptance_items(acceptance)

    kr_alpha_portfolio_pct = _kr_alpha_portfolio_weight(final, exposure)
    from src.alpha_shadow_policy import alpha_v02_brief_section

    alpha_v02_section = alpha_v02_brief_section(
        output_dir,
        data_dir=resolved_data,
        run_id=run_id or (final or {}).get("run_id"),
        kr_alpha_portfolio_pct=kr_alpha_portfolio_pct,
    )
    kr_alpha_investable_pct = alpha_v02_section.get("current_alpha_weight_pct")

    alpha_data_gate = ""
    alpha_candidate_count = 0
    if (output_dir / "alpha_candidates.csv").exists():
        with (output_dir / "alpha_candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
            alpha_candidate_count = sum(1 for _ in csv.DictReader(handle))
    gpt_ctx = read_output_json(output_dir / "gpt_context.json")
    if gpt_ctx:
        alpha_data_gate = str((gpt_ctx.get("alpha") or {}).get("data_gate") or "")

    kospi_dd = shadow_signals.get("kospi_drawdown_pct")
    if kospi_dd is None and triggers:
        for rev in triggers.get("kospi_drawdown_reviews") or []:
            if isinstance(rev, dict) and rev.get("drawdown_pct") is not None:
                kospi_dd = rev.get("drawdown_pct")
                break

    exec_metrics = count_executable_actions(final)
    watch_triggers = shadow_signals.get("watch_triggers") or []

    return {
        "date": str(date)[:10],
        "generated_at": generated_at,
        "report_version": REPORT_VERSION,
        "run_id": run_id or (final or {}).get("run_id", ""),
        "execution_authority": EXECUTION_AUTHORITY,
        "system_status": {
            "data_gate": auth.get("data_gate_config") or (final or {}).get("data_gate") or "",
            "unified_data_gate": auth.get("unified_data_gate") or "",
            "portfolio_gate": auth.get("portfolio_gate") or "",
            "alpha_sector_data_gate": auth.get("alpha_sector_data_gate") or "",
            "health_gate": tech.get("health_gate") or gates.get("health_gate", ""),
            "operational_status": auth.get("operational_status") or "",
            "technical_status": auth.get("technical_status") or "",
            "market_status": auth.get("market_status") or "",
            "full_status": auth.get("full_status") or "",
            "execution_scope": auth.get("execution_scope") or "",
            "authoritative_execution_scope": auth.get("authoritative_execution_scope") or auth.get("execution_scope") or "",
            "display_execution_scope": auth.get("display_execution_scope") or "",
            "execution_scope_explanation": auth.get("execution_scope_explanation") or "",
            "execution_permission": "NO_TRADE" if auth.get("no_trade") else "",
            "dry_run_days": (final or {}).get("dry_run_days", 0),
            "dry_run_required": gates.get("dry_run_required", 10),
            "policy_cap_active": bool(auth.get("policy_cap_active") if auth.get("policy_cap_active") is not None else cap.get("active")),
            "policy_cap_regime": auth.get("policy_cap_regime") or cap.get("cap_regime"),
            "policy_config_gate": (
                (read_output_json(output_dir / "gpt_context.json") or {}).get("policy_gate")
                or auth.get("data_gate_config")
                or (final or {}).get("data_gate")
            ),
            "policy_execution_cap": "ACTIVE" if bool(auth.get("policy_cap_active") if auth.get("policy_cap_active") is not None else cap.get("active")) else "inactive",
            "alpha_approval": (final or {}).get("alpha_approval", ""),
            "alpha_execution_status": (final or {}).get("alpha_execution_status", ""),
            "core_price_gate": core_gate,
            "acceptance_overall": auth.get("acceptance_overall") or "",
            "actual_buy_allowed": auth.get("actual_buy_allowed", 0),
            "030190_in_user_target": auth.get("030190_in_user_target", False),
            "030190_in_operational_target": auth.get("030190_in_operational_target", False),
        },
        "saa_taa": {
            "profile": (compass or {}).get("profile") or ((compass or {}).get("allocation") or {}).get("profile"),
            "computed_regime": (compass or {}).get("computed_regime", ""),
            "applied_regime": (compass or {}).get("applied_regime", ""),
            "market_phase": (compass or {}).get("computed_market_phase", ""),
            "compass_direction": (compass or {}).get("compass_direction", ""),
            "allocation_summary": _allocation_summary(compass),
            "top_group_gaps": _top_group_gaps(final),
        },
        "execution": {
            "operational_verdict": auth.get("operational_verdict")
            or (final or {}).get("operational_verdict", ""),
            "execution_scope": auth.get("execution_scope") or "",
            "authoritative_execution_scope": auth.get("authoritative_execution_scope") or auth.get("execution_scope") or "",
            "display_execution_scope": auth.get("display_execution_scope") or "",
            "execution_scope_explanation": auth.get("execution_scope_explanation") or "",
            "no_trade": auth.get("no_trade", False),
            "acceptance_overall": auth.get("acceptance_overall") or "",
            "full_status": auth.get("full_status") or "",
            "executable_action_count": exec_metrics["executable_buy_count"],
            "executable_buy_count": exec_metrics["executable_buy_count"],
            "actual_buy_allowed_count": exec_metrics["actual_buy_allowed_count"],
            "risk_reduce_trim_count": exec_metrics["risk_reduce_trim_count"],
            "allowed_risk_reduce_action_count": exec_metrics["allowed_risk_reduce_action_count"],
            "risk_reduce_trims": exec_metrics["risk_reduce_trims"],
        "alpha_new_buy": exec_metrics["alpha_new_buy"],
        "alpha_replace": exec_metrics["alpha_replace"],
        "core_etf_permission": (final or {}).get("execution_permissions", {}).get("core_etf_permission"),
        "alpha_auto_buy_permission": (final or {}).get("execution_permissions", {}).get(
            "alpha_auto_buy_permission"
        ),
        "alpha_research_permission": (final or {}).get("execution_permissions", {}).get(
            "alpha_research_permission"
        ),
        "main_block_reason": (final or {}).get("execution_permissions", {}).get("main_block_reason"),
        "sector_coverage": (final or {}).get("execution_permissions", {}).get("sector_coverage"),
        "alpha_sector_data_gate": (final or {}).get("execution_permissions", {}).get(
            "alpha_sector_data_gate"
        ),
        "manual_review_required": (final or {}).get("execution_permissions", {}).get(
            "manual_review_required"
        ),
        "fail_soft_patch_version": (final or {}).get("execution_permissions", {}).get(
            "patch_version", "v1.0.3"
        ),
            "top_actions": _top_actions(final),
        },
        "shadow_diagnostic": {
            "mode": (shadow or {}).get("mode", "shadow"),
            "signal_execution_mismatch": shadow_obs.get("signal_execution_mismatch", False),
            "primary_blocker": shadow_exec.get("primary_blocker", ""),
            "blocked_by": shadow_exec.get("blocked_by") or [],
            "execution_status": shadow_exec.get("status", ""),
            "theoretical_gap_krw": shadow_amounts.get("theoretical_gap_krw", 0),
            "reviewable_amount_krw": shadow_amounts.get("reviewable_amount_krw", 0),
            "actual_allowed_krw": shadow_amounts.get("actual_allowed_krw", 0),
            "vs_saa_mtd": shadow_perf.get("vs_saa_mtd"),
            "dip_buy_stage": shadow_signals.get("dip_buy_stage", ""),
            "buy_trigger_active": shadow_signals.get("buy_trigger_active", False),
        },
        "duration_sleeve": {
            "v1_cash_short_bond_target_pct": duration.get("v1_0_2_cash_short_bond_target_pct"),
            "v1_cash_short_bond_current_pct": duration.get("v1_0_2_cash_short_bond_current_pct"),
            "cash_short_pct": duration.get("cash_short_current_pct", 0),
            "kr_duration_pct": duration.get("kr_duration_bond_current_pct", 0),
            "global_duration_pct": duration.get("global_duration_bond_current_pct", 0),
            "duration_gap": duration.get("duration_gap", ""),
            "diagnosis": duration.get("diagnosis", ""),
            "execution_impact": duration.get("execution_impact", "none"),
        },
        "alpha_legacy": {
            "data_gate": alpha_data_gate,
            "candidate_count": alpha_candidate_count,
            "top_candidates": _top_alpha_candidates(output_dir),
        },
        "alpha_v0_2": alpha_v02_section,
        "alpha_v2": {
            "mode": (alpha_v2 or {}).get("mode", "shadow"),
            "schema_version": (alpha_v2 or {}).get("schema_version", ""),
            "coverage": (alpha_v2 or {}).get("coverage") or {},
            "execution_context": (alpha_v2 or {}).get("execution_context") or {},
            "policy_notes": (alpha_v2 or {}).get("policy_notes") or [],
            "target_write_occurred": False,
            "note": "Alpha v2 is shadow-only. Flow signal is not buy permission.",
        },
        "core_saa_reference": {
            "mode": (core_ref or {}).get("mode", "shadow_reference_only"),
            "authority": (core_ref or {}).get("authority", "none"),
            "diagnostic_only": (core_ref or {}).get("diagnostic_only", True),
            "schema_version": (core_ref or {}).get("schema_version", ""),
            "reference_slot_count": (core_ref or {}).get("reference_slot_count", 14),
            "summary": (core_ref or {}).get("summary") or {},
            "sleeve_target_pct": (core_ref or {}).get("sleeve_target_pct") or {},
            "sleeve_current_pct": (core_ref or {}).get("sleeve_current_pct") or {},
            "missing_core_count": len((core_ref or {}).get("missing_core") or []),
            "non_core_held_count": len((core_ref or {}).get("non_core_holdings") or []),
            "unresolved_ticker_count": (core_ref or {}).get("summary", {}).get("unresolved_ticker_count", 0),
            "validation_warnings": (core_ref or {}).get("validation_warnings") or [],
            "note": CORE_REFERENCE_DISCLAIMER,
        },
        "alpha_performance": {
            "mode": (alpha_perf or {}).get("mode", "shadow_diagnostic_only"),
            "authority": (alpha_perf or {}).get("authority", "none"),
            "diagnostic_only": (alpha_perf or {}).get("diagnostic_only", True),
            "metrics": (alpha_perf or {}).get("metrics") or {},
            "gate_opportunity_cost_count": (alpha_perf or {}).get("gate_opportunity_cost_count", 0),
            "weak_alpha_regime": ((alpha_perf or {}).get("metrics") or {}).get("weak_alpha_regime"),
            "note": ALPHA_DASHBOARD_DISCLAIMER,
        },
        "hakedaka_rerating": {
            "mode": (hakedaka_rerating or {}).get("mode", "shadow_diagnostic_only"),
            "authority": (hakedaka_rerating or {}).get("authority", "none"),
            "shadow_only": (hakedaka_rerating or {}).get("shadow_only", True),
            "candidate_count": (hakedaka_rerating or {}).get("candidate_count", 0),
            "preliminary_hunt_count": (hakedaka_rerating or {}).get("preliminary_hunt_count", 0),
            "primary_hunt_count": (hakedaka_rerating or {}).get("primary_hunt_count", 0),
            "overlap_count": (hakedaka_rerating or {}).get("overlap_count", 0),
            "hakedaka_only_count": (hakedaka_rerating or {}).get("hakedaka_only_count", 0),
            "top_candidates": (hakedaka_rerating or {}).get("top_candidates") or [],
            "note": RERATING_DISCLAIMER,
        },
        "hakedaka_data_quality": {
            "mode": (hakedaka_quality or {}).get("mode", "shadow_diagnostic_only"),
            "tier_h_price_coverage_pct": (hakedaka_quality or {}).get("tier_h_price_coverage_pct", 0),
            "missing_price_count": (hakedaka_quality or {}).get("missing_price_count", 0),
            "ocf_missing_count": (hakedaka_quality or {}).get("ocf_missing_count", 0),
            "debt_missing_count": (hakedaka_quality or {}).get("debt_missing_count", 0),
            "data_quality_below_60": (hakedaka_quality or {}).get("data_quality_below_60", 0),
            "verified_hunt_count": (hakedaka_quality or {}).get("verified_hunt_count", 0),
            "avg_data_quality_score": (hakedaka_quality or {}).get("avg_data_quality_score", 0),
            "financial_safety_verified_count": (hakedaka_quality or {}).get("financial_safety_verified_count", 0),
            "shareholder_return_verified_count": (hakedaka_quality or {}).get("shareholder_return_verified_count", 0),
            "note": DATA_QUALITY_DISCLAIMER,
        },
        "hakedaka_evidence": {
            "mode": (hakedaka_evidence or {}).get("mode", "shadow_evidence_pack"),
            "authority": (hakedaka_evidence or {}).get("authority", "none"),
            "shadow_only": (hakedaka_evidence or {}).get("shadow_only", True),
            "candidate_count": (hakedaka_evidence or {}).get("candidate_count", 0),
            "ocf_coverage_pct": ((hakedaka_fin_enrich or {}).get("coverage") or {}).get("ocf_pct", 0),
            "debt_coverage_pct": ((hakedaka_fin_enrich or {}).get("coverage") or {}).get("debt_pct", 0),
            "net_cash_coverage_pct": ((hakedaka_fin_enrich or {}).get("coverage") or {}).get("net_cash_pct", 0),
            "note": EVIDENCE_DISCLAIMER,
        },
        "hakedaka_coverage_audit": {
            "mode": (hakedaka_coverage or {}).get("mode", "shadow_coverage_audit"),
            "authority": (hakedaka_coverage or {}).get("authority", "none"),
            "shadow_only": (hakedaka_coverage or {}).get("shadow_only", True),
            "coverage": (hakedaka_coverage or {}).get("coverage") or {},
            "targets_pct": (hakedaka_coverage or {}).get("targets_pct") or {},
            "target_warnings": (hakedaka_coverage or {}).get("target_warnings") or [],
            "below_target": (hakedaka_coverage or {}).get("below_target", False),
            "top_missing_reason_categories": (hakedaka_coverage or {}).get("top_missing_reason_categories") or [],
            "missing_reason_aggregation": (hakedaka_coverage or {}).get("missing_reason_aggregation") or {},
            "low_coverage_diagnosis": (hakedaka_coverage or {}).get("low_coverage_diagnosis") or [],
            "financial_coverage_critical": (hakedaka_coverage or {}).get("financial_coverage_critical", False),
            "manual_review_top5": (hakedaka_coverage or {}).get("manual_review_top5") or [],
            "evidence_ready_candidate_count": (hakedaka_coverage or {}).get("evidence_ready_candidate_count")
            or (hakedaka_coverage or {}).get("actionable_candidate_count", 0),
            "execution_actionable_count": (hakedaka_coverage or {}).get("execution_actionable_count", 0),
            "investment_actionable_count": (hakedaka_coverage or {}).get("investment_actionable_count", 0),
            "top10_avg_missing_critical_fields": (hakedaka_coverage or {}).get("top10_avg_missing_critical_fields", 0),
            "note": COVERAGE_AUDIT_DISCLAIMER,
        },
        "latest_hakedaka_status": latest_hakedaka,
        "absolute_return_mandate": {
            "mode": absolute_return.get("mode"),
            "mode_label_ko": absolute_return.get("mode_label_ko"),
            "primary_objective": absolute_return.get("primary_objective"),
            "core_sleeve_target_pct": absolute_return.get("core_sleeve_target_pct"),
            "kr_alpha_overlay_max_pct": absolute_return.get("kr_alpha_overlay_max_pct"),
            "group_targets": absolute_return.get("group_targets") or {},
            "core_held_count": absolute_return.get("core_held_count"),
            "core_reference_count": absolute_return.get("core_reference_count"),
            "core_current_weight_sum_pct": absolute_return.get("core_current_weight_sum_pct"),
            "top_core_underweights": absolute_return.get("top_core_underweights") or [],
            "core_deployment_throttle": core_throttle,
            "ar1_parity": ar1_parity,
            "note": CORE_SAA_MANDATE_DISCLAIMER,
        },
        "ar2_accumulation_timing": {
            "phase": ar2_timing.get("phase", "AR-2"),
            "mode": ar2_timing.get("mode", "shadow_timing_only"),
            "execution_authority": ar2_timing.get("execution_authority", "none"),
            "disclaimer": AR2_DISCLAIMER,
            "readiness_disclaimer": ar2_timing.get("readiness_disclaimer", ""),
            "executable_count": ar2_timing.get("executable_count", 0),
            "ar21_qa": ar2_timing.get("ar21_qa") or {},
            "priority_ranking": ar2_timing.get("priority_ranking") or [],
            "rows": ar2_timing.get("rows") or [],
        },
        "early_alpha": {
            "phase": early_alpha.get("phase", "Early-Alpha-v0.1"),
            "mode": early_alpha.get("mode", "shadow_pilot_only"),
            "execution_authority": early_alpha.get("execution_authority", "none"),
            "disclaimer": EARLY_ALPHA_DISCLAIMER,
            "pilot_entry_count": early_alpha.get("pilot_entry_count", 0),
            "watch_count": early_alpha.get("watch_count", 0),
            "confirmation_candidate_count": early_alpha.get("confirmation_candidate_count", 0),
            "top_pilot": early_alpha.get("top_pilot") or [],
            "top_watch": early_alpha.get("top_watch") or [],
        },
        "alpha_opportunity": {
            "phase": opportunity.get("phase", "Alpha-Opportunity-v0.2"),
            "mode": opportunity.get("mode", "shadow_pilot_only"),
            "execution_authority": opportunity.get("execution_authority", "none"),
            "disclaimer": OPPORTUNITY_DISCLAIMER,
            "candidate_count": opportunity.get("candidate_count", 0),
            "pilot_entry_count": opportunity.get("pilot_entry_count", 0),
            "watch_count": opportunity.get("watch_count", 0),
            "confirmation_candidate_count": opportunity.get("confirmation_candidate_count", 0),
            "top_pilot": opportunity.get("top_pilot") or [],
            "top_watch": opportunity.get("top_watch") or [],
        },
        "opportunity_analytics": {
            "phase": opp_analytics.get("phase", "Alpha-Opportunity-Analytics-v0.3"),
            "mode": opp_analytics.get("mode", "shadow_learning_only"),
            "disclaimer": opp_analytics.get("disclaimer", ""),
            "active_signals": opp_analytics.get("active_signals", 0),
            "closed_signals": opp_analytics.get("closed_signals", 0),
            "failure_database": opp_analytics.get("failure_database") or {},
            "top_pilot_analytics": opp_analytics.get("top_pilot_analytics") or [],
        },
        "shadow_cash_floor_ladder": {
            "mode": shadow_ladder.get("mode", "shadow_reference_only"),
            "execution_authority": shadow_ladder.get("execution_authority", "none"),
            "current_cash_short_bond_pct": shadow_ladder.get("current_cash_short_bond_pct"),
            "floor_pct": shadow_ladder.get("floor_pct"),
            "deployable_from_cash_pct": shadow_ladder.get("deployable_from_cash_pct"),
            "buy_1_max_from_cash_pct": shadow_ladder.get("buy_1_max_from_cash_pct"),
            "buy_1_ready": shadow_ladder.get("buy_1_ready", False),
            "data_gate": shadow_ladder.get("data_gate"),
            "dry_run_days": shadow_ladder.get("dry_run_days"),
            "dry_run_required": shadow_ladder.get("dry_run_required"),
            "summary_line": shadow_ladder.get("summary_line", ""),
            "note": SHADOW_LADDER_DISCLAIMER,
        },
        "dart_accounts_debug": {
            "mode": (dart_accounts_debug or {}).get("mode", "shadow_only"),
            "phase": (dart_accounts_debug or {}).get("phase", "4e"),
            "success_rate_pct": ((dart_accounts_debug or {}).get("summary") or {}).get("success_rate_pct", 0),
            "dominant_failure_category": ((dart_accounts_debug or {}).get("summary") or {}).get("dominant_failure_category", ""),
            "recommended_next_action": ((dart_accounts_debug or {}).get("summary") or {}).get("recommended_next_action", ""),
            "coverage_before": ((dart_accounts_debug or {}).get("summary") or {}).get("coverage_before") or {},
            "coverage_after": ((dart_accounts_debug or {}).get("summary") or {}).get("coverage_after") or {},
            "raw_samples_saved": ((dart_accounts_debug or {}).get("summary") or {}).get("raw_samples_saved") or [],
            "note": ACCOUNTS_DEBUG_DISCLAIMER,
        },
        "hakedaka_nav_treasury": {
            "mode": (hakedaka_phase4f or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4f or {}).get("phase", "4f"),
            "coverage_before": (hakedaka_phase4f or {}).get("coverage_before") or {},
            "coverage_after": (hakedaka_phase4f or {}).get("coverage_after") or {},
            "summary": (hakedaka_phase4f or {}).get("summary") or {},
            "note": NAV_TREASURY_DISCLAIMER,
        },
        "hakedaka_manual_verification": {
            "mode": (hakedaka_phase4g or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4g or {}).get("phase", "4g"),
            "summary": (hakedaka_phase4g or {}).get("summary") or {},
            "nav_queue_top5": (hakedaka_phase4g or {}).get("nav_queue_top5") or [],
            "top_blockers_sample": (hakedaka_phase4g or {}).get("top_blockers_sample") or [],
            "note": MANUAL_VERIFICATION_DISCLAIMER,
        },
        "hakedaka_catalyst_evidence": {
            "mode": (hakedaka_phase4h or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4h or {}).get("phase", "4h"),
            "summary": (hakedaka_phase4h or {}).get("summary") or {},
            "fetch_stats": (hakedaka_phase4h or {}).get("fetch_stats") or {},
            "note": CATALYST_EVIDENCE_DISCLAIMER,
        },
        "hakedaka_catalyst_calibration": {
            "mode": (hakedaka_phase4h1 or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4h1 or {}).get("phase", "4h-1"),
            "summary": (hakedaka_phase4h1 or {}).get("summary") or {},
            "watchlist_top5": (hakedaka_phase4h1 or {}).get("watchlist_top5") or [],
            "note": CALIBRATION_DISCLAIMER,
        },
        "hakedaka_forward_return_tracking": {
            "mode": (hakedaka_phase4i or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4i or {}).get("phase", "4i"),
            "summary": (hakedaka_phase4i or {}).get("summary") or {},
            "note": FORWARD_RETURN_DISCLAIMER,
        },
        "hakedaka_forward_return_qa": {
            "mode": (hakedaka_phase4i1 or {}).get("mode", "shadow_only"),
            "phase": (hakedaka_phase4i1 or {}).get("phase", "4i-1"),
            "summary": (hakedaka_phase4i1 or {}).get("summary") or {},
            "note": FORWARD_RETURN_QA_DISCLAIMER,
        },
        "market": {
            "regime": (compass or {}).get("applied_regime", ""),
            "kospi_drawdown_pct": kospi_dd,
            "watch_triggers": watch_triggers,
            "watch_trigger_count": len(watch_triggers),
            "active_triggers": watch_triggers,
            "all_active_triggers": shadow_signals.get("active_triggers") or [],
            "suppressed_triggers": shadow_signals.get("suppressed_triggers") or [],
            "risk_reduce_trigger_count": shadow_signals.get("risk_reduce_trigger_count", 0),
            "scores": (compass or {}).get("scores") or {},
        },
        "acceptance": {
            "overall": (acceptance or {}).get("overall", ""),
            "technical_overall": (acceptance or {}).get("technical_overall", ""),
            "operational_overall": (acceptance or {}).get("operational_overall", ""),
            "fail_items": fail_items,
            "warn_items": warn_items[:10],
        },
        "references": {
            "authoritative_execution": "final_execution_decision.json",
            "satellite_target": "data/target_portfolio.csv",
            "core_reference": "data/core_saa_reference.yaml",
            "core_diagnostic": "core_saa_reference_diagnostic.json",
            "full_audit_bundle": "ai_export_bundle.json",
            "human_report": "daily_report.md",
            "note": "GPT Report v2.0 입력. execution_authority v1.0.2 우선. Core reference는 shadow.",
        },
    }


def _fmt_optional_pct(value: Any, *, suffix: str = "%") -> str:
    if value is None or value == "" or value == "None":
        return "n/a"
    return f"{value}{suffix}"


def _fmt_kospi_excess(metrics: dict[str, Any]) -> str:
    """Never treat missing KOSPI200 bench as 0 — show n/a when excess is null/stale."""
    excess = metrics.get("kr_alpha_excess_vs_kospi200_mtd")
    kospi = metrics.get("kospi200_return_mtd")
    quality = str(metrics.get("kospi200_return_quality") or "")
    if excess is None or kospi is None or quality in {"stale_price", "insufficient_history", "missing_ticker", "no_prices"}:
        reason = quality or "benchmark_unavailable"
        return f"n/a ({reason}) — not {metrics.get('kr_alpha_return_mtd', '—')}%p"
    return f"{excess}%p"


def build_daily_report_v2_sections(brief: dict[str, Any]) -> list[str]:
    """daily_brief → daily_report 상단 shadow/alpha/duration 요약 (중복 JSON 파싱 제거)."""
    sys_s = brief.get("system_status") or {}
    saa = brief.get("saa_taa") or {}
    shadow = brief.get("shadow_diagnostic") or {}
    duration = brief.get("duration_sleeve") or {}
    alpha = brief.get("alpha_v0_2") or {}
    core_ref = brief.get("core_saa_reference") or {}
    alpha_perf = brief.get("alpha_performance") or {}
    hk_rerating = brief.get("hakedaka_rerating") or {}
    hk_quality = brief.get("hakedaka_data_quality") or {}
    hk_evidence = brief.get("hakedaka_evidence") or {}
    hk_coverage = brief.get("hakedaka_coverage_audit") or {}
    dart_acct = brief.get("dart_accounts_debug") or {}
    hk_nav = brief.get("hakedaka_nav_treasury") or {}
    hk_manual = brief.get("hakedaka_manual_verification") or {}
    hk_catalyst = brief.get("hakedaka_catalyst_evidence") or {}
    hk_calib = brief.get("hakedaka_catalyst_calibration") or {}
    hk_forward = brief.get("hakedaka_forward_return_tracking") or {}
    hk_forward_qa = brief.get("hakedaka_forward_return_qa") or {}
    hk_latest = brief.get("latest_hakedaka_status") or {}
    abs_return = brief.get("absolute_return_mandate") or {}
    ar2 = brief.get("ar2_accumulation_timing") or {}
    early = brief.get("early_alpha") or {}
    opp = brief.get("alpha_opportunity") or {}
    opp_a = brief.get("opportunity_analytics") or {}
    shadow_ladder = brief.get("shadow_cash_floor_ladder") or {}
    vs = shadow.get("vs_saa_mtd")
    vs_line = f" · vs SAA MTD {vs:+.2f}%p" if vs is not None else ""
    exec_block = brief.get("execution") or {}
    trims = exec_block.get("risk_reduce_trims") or []
    trim_line = "none"
    if trims:
        t = trims[0]
        trim_line = (
            f"{t.get('ticker')} only, max {abs(float(t.get('allowed_size_pct') or 0)):.1f}%p, "
            f"human approval required"
        )
    dry = sys_s.get("dry_run_days", "—")
    dry_req = sys_s.get("dry_run_required", 10)
    live_note = "live approval not yet granted" if isinstance(dry, int) and dry < dry_req else ""

    if alpha.get("status") == "disabled" or alpha.get("enabled") is False:
        alpha_v02_line = "- **Alpha v0.2 shadow**: disabled"
    else:
        alpha_v02_line = (
            f"- **Alpha v0.2 (shadow)**: {alpha.get('alpha_budget_status', '—')} · "
            f"투자자산 기준 {alpha.get('current_alpha_weight_pct', 0)}% · "
            f"**전체 포트(v1.0.2) {fmt_pct_with_suffix(alpha.get('kr_alpha_v1_portfolio_pct'))}** · "
            f"new_buy `{alpha.get('new_alpha_buy_allowed', False)}`"
        )

    lines: list[str] = []
    lines.extend([
        "## Report v2.0 요약 (GPT 입력 = daily_brief.json)",
        f"- **Actual Buy Allowed**: {exec_block.get('actual_buy_allowed_count', 0)} · "
        f"**Risk-reduce Trim Candidates**: {exec_block.get('risk_reduce_trim_count', 0)} · "
        f"Alpha New Buy: `{exec_block.get('alpha_new_buy', 'BLOCKED')}` · "
        f"Alpha Replace: `{exec_block.get('alpha_replace', 'BLOCKED')}`",
    ])
    auth_scope = sys_s.get("authoritative_execution_scope") or sys_s.get("execution_scope") or "—"
    display_scope = sys_s.get("display_execution_scope") or ""
    if auth_scope == "NO_TRADE" or int(exec_block.get("actual_buy_allowed_count") or 0) == 0:
        lines.append(
            f"- **Authoritative scope**: **NO_TRADE — 신규매수 없음** · "
            f"Actual Buy Allowed **0**"
        )
        if display_scope and display_scope != "NO_TRADE":
            lines.append(
                f"- **Policy/display scope**: `{display_scope}` — ETF_ONLY는 ETF 매수 허가가 아님"
            )
    lines.append(
        f"- **상태**: `{sys_s.get('operational_status', '—')}` · scope `{auth_scope}` · "
        f"gate `{sys_s.get('data_gate', '—')}` · dry-run {dry}/{dry_req}{(' · ' + live_note) if live_note else ''}",
    )
    lines.extend([
        f"- **SAA/TAA**: {saa.get('profile', '—')} · {saa.get('applied_regime', '—')} · {saa.get('market_phase', '—')}",
        f"- **Shadow**: blocker `{shadow.get('primary_blocker', '—')}` · mismatch `{shadow.get('signal_execution_mismatch', False)}`"
        f"{vs_line}",
        f"- **Duration**: cash {duration.get('cash_short_pct', 0)}% · kr_duration {duration.get('kr_duration_pct', 0)}% · "
        f"gap `{duration.get('duration_gap', '—')}` · {duration.get('diagnosis', '')}",
        alpha_v02_line,
        "",
    ])

    if abs_return.get("mode"):
        uw = abs_return.get("top_core_underweights") or []
        uw_line = ", ".join(
            f"{u.get('name')}({u.get('gap_pct')}%p)" for u in uw[:3]
        ) if uw else "—"
        gt = abs_return.get("group_targets") or {}
        throttle = abs_return.get("core_deployment_throttle") or {}
        limits = throttle.get("limits") or {}
        parity = abs_return.get("ar1_parity") or {}
        lines.extend([
            "## Core SAA Mandate (Phase AR-1 — operating policy)",
            f"> {CORE_SAA_MANDATE_DISCLAIMER}",
            f"- **모드**: {abs_return.get('mode_label_ko', 'Core SAA 기준 초과수익 운영 모드')}",
            f"- **목표**: Core 슬리브 {abs_return.get('core_sleeve_target_pct')}% + kr_alpha ≤{abs_return.get('kr_alpha_overlay_max_pct')}% + CASH 3%",
            f"- **Core 보유**: {abs_return.get('core_held_count')}/{abs_return.get('core_reference_count')} · "
            f"current sum {abs_return.get('core_current_weight_sum_pct', '—')}%",
            f"- **그룹 target**: cash {gt.get('cash_short_bond', '—')}% · global {gt.get('global_beta', '—')}% · "
            f"income {gt.get('income_alt', '—')}% · hedge {gt.get('hedge_alt', '—')}% · kr_alpha {gt.get('kr_alpha', '—')}%",
            f"- **Core underweight (top)**: {uw_line}",
            f"- **배치 throttle**: 1회 {limits.get('per_trade_max_pct', 3)}%p · 주간 {limits.get('weekly_max_pct', 5)}%p · "
            f"월간 {limits.get('monthly_max_pct', 10)}%p · gate `{throttle.get('gate_allowed', False)}`",
            f"- **069500 KODEX200**: Core 14-slot 미포함 — 국내 주식은 kr_alpha 위성",
            f"- **미국달러단기채 6.25%**: ticker unresolved · 157450 임시 합산 (달러 노출 대체 아님)",
            f"- **슬롯**: {parity.get('framework_label', '14-slot / 12 active Core ETF')}",
            f"- **AR-1 parity**: `{parity.get('all_pass', '—')}` · final_trades {parity.get('final_trade_count', '—')} · "
            f"throttle gate `{parity.get('throttle_gate_allowed', '—')}`",
            "- legacy 55% cash floor **폐기** — 단계적 Core underweight 채우기",
            "",
        ])

    if ar2.get("rows"):
        qa = ar2.get("ar21_qa") or {}
        readiness = ar2.get("readiness_disclaimer") or (
            "Timing Watch/Ready ≠ Buy permission. Execution blocked unless executable=true."
        )
        stale_prohibited = any(r.get("execution_prohibited_stale") for r in ar2.get("rows") or [])
        lines.extend([
            "## Asset-Specific Accumulation Timing (AR-2.1, shadow only)",
            f"> {AR2_DISCLAIMER}",
            f"> **{readiness}**",
        ])
        if stale_prohibited:
            lines.append(
                "> **Stale critical input detected** — timing score is shadow-only; "
                "**execution prohibited** (e.g. korea_10y_stale, reit_price_history_short)."
            )
        lines.extend([
            f"> executable_count `{ar2.get('executable_count', 0)}` · "
            f"watch_but_blocked `{qa.get('watch_but_blocked_count', 0)}` · "
            f"ready_but_blocked `{qa.get('ready_but_blocked_count', 0)}`",
            "",
            "| 자산군 | Gap | Timing | Status | Input | stale | Execution | 해석 |",
            "|--------|-----|--------|--------|-------|-------|-----------|------|",
        ])
        for row in ar2.get("rows") or []:
            gap = row.get("underweight_gap_pct")
            gap_s = f"+{gap:.1f}%p" if isinstance(gap, (int, float)) and gap > 0 else (
                f"-{row.get('overweight_gap_pct', 0):.1f}%p"
                if row.get("overweight_gap_pct")
                else f"{gap}%p" if gap is not None else "—"
            )
            score = row.get("timing_score")
            score_s = str(score) if score is not None else "N/A"
            stale = row.get("stale_inputs") or []
            if isinstance(stale, list):
                stale_s = ", ".join(stale[:3]) if stale else "—"
            else:
                stale_s = str(stale) or "—"
            note = row.get("timing_execution_note") or row.get("recommended_note") or "—"
            lines.append(
                f"| {row.get('asset_group', '—')} | {gap_s} | {score_s} | "
                f"{row.get('timing_status', '—')} | {row.get('input_quality', '—')} | {stale_s} | "
                f"{row.get('execution_status', '—')} | {note} |"
            )
        duration_row = next((r for r in ar2.get("rows") or [] if r.get("asset_group") == "duration_bond"), None)
        if duration_row and duration_row.get("duration_components"):
            comp = duration_row["duration_components"]
            kr = comp.get("duration_kr") or {}
            us = comp.get("duration_us") or {}
            lines.extend([
                "",
                f"- **duration_kr** ({kr.get('ticker', '148070')}): score {kr.get('timing_score', '—')} · "
                f"stale {kr.get('stale_inputs') or '—'}",
                f"- **duration_us** ({us.get('ticker', '308620')}): score {us.get('timing_score', '—')} · "
                f"stale {us.get('stale_inputs') or '—'} · {us.get('note', '')}",
            ])
        lines.append("")

    if opp.get("top_pilot") or opp.get("top_watch") or opp.get("candidate_count", 0) > 0:
        lines.extend([
            "## Alpha Opportunity Engine (v0.2 — shadow pilot only)",
            f"> {OPPORTUNITY_DISCLAIMER}",
            f"> **Opportunity signal ≠ Confirmation buy.** Pilot only; final trades follow `final_execution_decision`.",
            f"- universe `{opp.get('candidate_count', 0)}` · pilot `{opp.get('pilot_entry_count', 0)}` · "
            f"watch `{opp.get('watch_count', 0)}` · confirmation `{opp.get('confirmation_candidate_count', 0)}`",
            "",
            "| Ticker | Score | Grade | Shadow signal | Pilot size | Stop | Missing confirmation | Do-not-chase |",
            "|--------|-------|-------|---------------|------------|------|----------------------|--------------|",
        ])
        shown: set[str] = set()
        for row in (opp.get("top_pilot") or []) + (opp.get("top_watch") or [])[:5]:
            tk = str(row.get("ticker", ""))
            if tk in shown:
                continue
            shown.add(tk)
            shadow_lbl = shadow_opportunity_action_label(str(row.get("allowed_action", "")))
            lines.append(
                f"| {tk} | {row.get('total_score', '—')} | {row.get('opportunity_grade', '—')} | "
                f"{shadow_lbl} | {row.get('allowed_position_fraction', 0)} | "
                f"{row.get('stop_level', '—')} | {str(row.get('missing_confirmation', '—'))[:40]} | "
                f"{str(row.get('do_not_chase_zone', '—'))[:30]} |"
            )
        lines.append("")

    if opp_a.get("top_pilot_analytics") or opp_a.get("failure_database"):
        fdb = opp_a.get("failure_database") or {}
        closed_n = int(opp_a.get("closed_signals") or fdb.get("total_closed") or 0)
        heuristic_note = (
            " · **Prob/Exp α = heuristic — not statistically validated**"
            if closed_n < 30
            else ""
        )
        lines.extend([
            "### Opportunity Analytics (v0.3 — learning shadow)",
        ])
        if closed_n < 30:
            lines.append("> **Heuristic only · Not statistically validated · Do not use for investment decision**")
            lines.append("> Validation sample: 0 closed signals · Investment use: **prohibited**")
        lines.extend([
            f"- active `{opp_a.get('active_signals', 0)}` · closed `{closed_n}` · "
            f"overall success rate `{fmt_rate_pct_display(fdb.get('overall_success_rate_pct'), closed_count=closed_n)}`{heuristic_note}",
            "",
            "| Ticker | Type | Score | Heuristic† | Exp α est.† | Hold(d) | Age(d) | Pilot |",
            "|--------|------|-------|------------|-------------|---------|--------|-------|",
        ])
        if closed_n < 30:
            lines.append("> † research-only estimate — not success probability")
            lines.append("")
        for row in opp_a.get("top_pilot_analytics") or []:
            lines.append(
                f"| {row.get('ticker')} | {row.get('opportunity_type', '—')} | {row.get('total_score')} | "
                f"{row.get('success_probability_pct', '—')}% | +{row.get('expected_alpha_pct', '—')}% | "
                f"{row.get('expected_holding_days', '—')} | {row.get('opportunity_age_days', 0)} | "
                f"{shadow_opportunity_action_label(str(row.get('allowed_action', '')))} |"
            )
        by_type = fdb.get("by_opportunity_type") or {}
        if by_type:
            lines.append("")
            lines.append("**Success rate by type (closed signals only):**")
            for t, stats in sorted(by_type.items()):
                lines.append(
                    f"- {t}: {stats.get('success_rate_pct', '—')}% "
                    f"({stats.get('success', 0)}/{stats.get('total', 0)})"
                )
        lines.append("")

    if early.get("top_pilot") or early.get("top_watch") or early.get("pilot_entry_count", 0) > 0:
        lines.extend([
            "## Early Alpha Engine (v0.1 legacy — shadow pilot only)",
            f"> {EARLY_ALPHA_DISCLAIMER}",
            f"> **Early signal ≠ Confirmation buy.** Pilot only; final trades follow `final_execution_decision`.",
            f"- pilot `{early.get('pilot_entry_count', 0)}` · watch `{early.get('watch_count', 0)}` · "
            f"confirmation `{early.get('confirmation_candidate_count', 0)}`",
            "",
            "| Ticker | Score | Grade | Early signal | Pilot size | Stop | Confirmation trigger |",
            "|--------|-------|-------|--------------|------------|------|------------------------|",
        ])
        shown = (early.get("top_pilot") or []) + (early.get("top_watch") or [])[:3]
        seen: set[str] = set()
        for row in shown:
            tk = row.get("ticker", "")
            if tk in seen:
                continue
            seen.add(tk)
            lines.append(
                f"| {tk} | {row.get('total_score', '—')} | {row.get('early_grade', '—')} | "
                f"{shadow_opportunity_action_label(str(row.get('allowed_action', '')))} | {row.get('allowed_position_fraction', 0)} | "
                f"{row.get('stop_level', '—')} | {row.get('confirmation_trigger') or row.get('do_not_chase_zone') or '—'} |"
            )
        lines.append("")

    if shadow_ladder.get("summary_line"):
        lines.extend([
            "## Cash Floor Ladder (shadow only)",
            f"> {SHADOW_LADDER_DISCLAIMER}",
            f"- {shadow_ladder.get('summary_line')}",
            f"- **buy_1_ready**: `{shadow_ladder.get('buy_1_ready', False)}` "
            f"(gate `{shadow_ladder.get('data_gate', '—')}`, "
            f"dry-run {shadow_ladder.get('dry_run_days', '—')}/{shadow_ladder.get('dry_run_required', 10)})",
            "",
        ])

    if hk_latest.get("mode"):
        lines.extend([
            "## Hakedaka Latest Status (shadow only)",
            f"> {HAKEDAKA_STATUS_DISCLAIMER}",
            f"- **data_ready**: `{hk_latest.get('data_ready', False)}` · "
            f"**catalyst_extraction_ready**: `{hk_latest.get('catalyst_extraction_ready', False)}` · "
            f"**forward_return_pending**: `{hk_latest.get('forward_return_pending', True)}`",
            f"- **execution actionable**: {hk_latest.get('execution_actionable_count', 0)} · "
            f"**investment actionable**: {hk_latest.get('investment_actionable_count', 0)} · "
            f"**evidence-ready (data)**: {hk_latest.get('evidence_ready_candidate_count', 0)}",
            f"- **execution_authority**: `{hk_latest.get('execution_authority', 'none')}` · "
            f"effective_signal: {hk_latest.get('effective_signal_date', '—')} · "
            f"next 5D checkpoint: {hk_latest.get('next_forward_checkpoint_5d', '—')}",
            "",
        ])

    if core_ref.get("mode"):
        summ = core_ref.get("summary") or {}
        lines.extend([
            "## Core SAA reference (shadow — authority none)",
            f"> {CORE_REFERENCE_DISCLAIMER}",
            f"- **Target vs current (Core slots)**: {summ.get('core_target_weight_sum_pct', '—')}% vs "
            f"{summ.get('core_current_weight_sum_pct', '—')}% · gap {summ.get('core_gap_sum_pct', '—')}%p",
            f"- **Held**: {summ.get('core_held_count', '—')}/{summ.get('core_reference_count', 14)} · "
            f"missing {core_ref.get('missing_core_count', 0)} · non-Core {core_ref.get('non_core_held_count', 0)} · "
            f"unresolved ticker {core_ref.get('unresolved_ticker_count', 0)}",
            f"- **diagnostic_only**: `{core_ref.get('diagnostic_only', True)}` · schema `{core_ref.get('schema_version', '—')}`",
            "",
        ])

    if alpha_perf.get("mode"):
        m = alpha_perf.get("metrics") or {}
        lines.extend([
            "## SAA-relative Alpha Dashboard (shadow only)",
            f"> {ALPHA_DASHBOARD_DISCLAIMER}",
            f"- **Core SAA MTD**: {m.get('core_saa_return_mtd', '—')}% · "
            f"**Actual (judgment)**: {m.get('actual_portfolio_return_mtd', '—')}% "
            f"(source=`{m.get('actual_return_source', '—')}`) · "
            f"**Excess vs Core**: {m.get('excess_return_vs_core_mtd', '—')}%p",
            (
                f"- **NAV raw MTD**: {m.get('raw_nav_return_mtd', '—')}% · "
                f"**NAV adjusted**: {m.get('adjusted_nav_return_mtd', '—')}% · "
                f"external_flow≈{m.get('estimated_external_flow_mtd_krw', '—')} "
                f"(raw ≠ trading alpha)"
            ),
            (
                f"- **kr_alpha MTD**: {m.get('kr_alpha_return_mtd', '—')}% · "
                f"**KOSPI200**: {_fmt_optional_pct(m.get('kospi200_return_mtd'))} "
                f"(quality=`{m.get('kospi200_return_quality', '—')}`)"
            ),
            (
                f"- **kr_alpha vs KOSPI200 MTD**: {_fmt_kospi_excess(m)} · "
                f"weak_alpha_regime `{m.get('weak_alpha_regime', False)}`"
            ),
            (
                f"- **Core SAA 갭 기회비용(MTD, shadow)**: "
                f"{_fmt_optional_pct(m.get('core_saa_gap_opportunity_cost_mtd'), suffix='%p')} "
                f"(총 갭 {_fmt_optional_pct(m.get('core_saa_total_gap_pct'), suffix='%p')}) "
                f"— 실행 게이트 미변경, 진단 전용"
            ),
            (
                f"- **Core SAA 갭 기회비용 (since "
                f"{m.get('core_saa_gap_inception_date') or '2026-06-17'}, shadow, 근사)**: "
                f"{_fmt_optional_pct(m.get('core_saa_gap_opportunity_cost_since_inception'), suffix='%p')} "
                f"— 오늘 갭이 가동 이후 유지됐다는 가정, 상한선 추정치"
            ),
            f"- **Gate**: theoretical buys {m.get('theoretical_buy_count', 0)} · executable {m.get('executable_buy_count', 0)} · "
            f"blocked rows {alpha_perf.get('gate_opportunity_cost_count', 0)}",
            "",
        ])

    if hk_rerating.get("mode"):
        top_hk = hk_rerating.get("top_candidates") or []
        top_line = ", ".join(
            f"{t.get('name')}({t.get('score')})" for t in top_hk[:5]
        ) if top_hk else "—"
        lines.extend([
            "## Hakedaka Re-rating Screener (shadow only)",
            f"> {RERATING_DISCLAIMER}",
            f"- **후보**: {hk_rerating.get('candidate_count', 0)} · preliminary {hk_rerating.get('preliminary_hunt_count', 0)} · "
            f"verified {hk_rerating.get('primary_hunt_count', 0)} · "
            f"QVM overlap {hk_rerating.get('overlap_count', 0)} · hakedaka-only {hk_rerating.get('hakedaka_only_count', 0)}",
            f"- **Top 5**: {top_line}",
            f"- **shadow_only**: `{hk_rerating.get('shadow_only', True)}` · authority `{hk_rerating.get('authority', 'none')}`",
            "",
        ])

    if hk_quality.get("mode"):
        lines.extend([
            "## Hakedaka Data Quality (shadow only)",
            f"> {DATA_QUALITY_DISCLAIMER}",
            f"- **Tier H price coverage**: {hk_quality.get('tier_h_price_coverage_pct', 0)}% · "
            f"missing price {hk_quality.get('missing_price_count', 0)} · "
            f"OCF missing {hk_quality.get('ocf_missing_count', 0)} · debt missing {hk_quality.get('debt_missing_count', 0)}",
            f"- **data_quality < 60**: {hk_quality.get('data_quality_below_60', 0)}종 · "
            f"verified hunt {hk_quality.get('verified_hunt_count', 0)} · "
            f"avg score {hk_quality.get('avg_data_quality_score', 0)}",
            "- 낮은 품질 후보는 **preliminary research candidate** — 매수 권고 아님",
            "",
        ])

    if hk_evidence.get("mode"):
        lines.extend([
            "## Hakedaka Evidence Enrichment (shadow only)",
            f"> {EVIDENCE_DISCLAIMER}",
            f"- **Top10 evidence pack**: {hk_evidence.get('candidate_count', 0)}종 · "
            f"OCF coverage {hk_evidence.get('ocf_coverage_pct', 0)}% · "
            f"debt {hk_evidence.get('debt_coverage_pct', 0)}% · "
            f"net cash {hk_evidence.get('net_cash_coverage_pct', 0)}%",
            f"- **financial_safety_verified**: {hk_quality.get('financial_safety_verified_count', 0)}종 · "
            f"**shareholder_return_verified**: {hk_quality.get('shareholder_return_verified_count', 0)}종",
            "- evidence pack은 **사람 검토용** — execution 권한 없음",
            "",
        ])

    if hk_coverage.get("mode"):
        cov = hk_coverage.get("coverage") or {}
        targets = hk_coverage.get("targets_pct") or {}
        warn_lines = []
        for w in hk_coverage.get("target_warnings") or []:
            warn_lines.append(
                f"**WARN** {w.get('metric')}: {w.get('actual_pct')}% < target {w.get('target_pct')}%"
            )
        review_top = hk_coverage.get("manual_review_top5") or []
        review_line = ", ".join(
            f"{r.get('ticker')}" for r in review_top[:5]
        ) if review_top else "—"
        missing_top = hk_coverage.get("top_missing_reason_categories") or []
        agg = hk_coverage.get("missing_reason_aggregation") or {}
        if agg.get("by_category"):
            missing_line = ", ".join(
                f"{m.get('category')}({m.get('count')})" for m in agg.get("by_category", [])[:3]
            )
        else:
            missing_line = ", ".join(
                f"{m.get('category')}({m.get('count')})" for m in missing_top[:3]
            ) if missing_top else "—"
        p0 = hk_coverage.get("low_coverage_diagnosis") or []
        p0_line = p0[0].get("recommended_action", "") if p0 else "—"
        lines.extend([
            "## Hakedaka Coverage Audit (shadow only)",
            f"> {COVERAGE_AUDIT_DISCLAIMER}",
            f"- **OCF**: {cov.get('ocf_coverage', 0)}% (target {targets.get('ocf_coverage', 70)}%) · "
            f"**FCF**: {cov.get('fcf_coverage', 0)}% · **debt**: {cov.get('debt_coverage', 0)}% · "
            f"**cash**: {cov.get('cash_coverage', 0)}% · **net_cash**: {cov.get('net_cash_coverage', 0)}%",
            f"- **treasury_scan**: {cov.get('treasury_scan_coverage', 0)}% (target {targets.get('treasury_scan_coverage', 80)}%) · "
            f"**treasury_event_found** (info): {cov.get('treasury_event_found_rate', 0)}%",
            f"- **target 미달 WARN**: {len(hk_coverage.get('target_warnings') or [])}건 · "
            f"top missing: {missing_line}",
            f"- **P0 diagnosis**: {p0_line}",
            f"- **manual review queue (top 5)**: {review_line}",
            f"- **actionable 구분 (shadow)**: execution {hk_coverage.get('execution_actionable_count', 0)} · "
            f"investment {hk_coverage.get('investment_actionable_count', 0)} · "
            f"evidence-ready (data) {hk_coverage.get('evidence_ready_candidate_count') or hk_coverage.get('actionable_candidate_count', 0)} · "
            f"top10 avg missing critical: {hk_coverage.get('top10_avg_missing_critical_fields', 0)}",
        ])
        if warn_lines:
            lines.append("- " + " · ".join(warn_lines[:3]))
        lines.extend([
            "- 커버리지 WARN은 **매수/매도 권고가 아님** — 데이터가 낮으면 하케다카 점수 신뢰도도 낮음",
            "",
        ])

    if dart_acct.get("phase") or dart_acct.get("success_rate_pct") is not None:
        cov_before = dart_acct.get("coverage_before") or {}
        cov_after = dart_acct.get("coverage_after") or {}
        raw_n = len(dart_acct.get("raw_samples_saved") or [])
        lines.extend([
            "## DART Accounts Fetch Debug (shadow only)",
            f"> {ACCOUNTS_DEBUG_DISCLAIMER}",
            f"- **accounts fetch success rate**: {dart_acct.get('success_rate_pct', 0)}%",
            f"- **dominant failure**: {dart_acct.get('dominant_failure_category') or '—'} · "
            f"action: {dart_acct.get('recommended_next_action') or '—'}",
            f"- **OCF coverage**: before {cov_before.get('ocf_coverage', '—')}% -> "
            f"after {cov_after.get('ocf_coverage', '—')}% · "
            f"debt: {cov_before.get('debt_coverage', '—')}% -> {cov_after.get('debt_coverage', '—')}%",
            f"- **raw samples saved**: {raw_n} files",
            "- 재무계정 커버리지 개선 전까지 하케다카 후보는 **preliminary research candidate**",
            "",
        ])

    if hk_nav.get("phase"):
        s4f = hk_nav.get("summary") or {}
        cov_a = hk_nav.get("coverage_after") or {}
        lines.extend([
            "## Hakedaka NAV & Treasury Precision (shadow only)",
            f"> {NAV_TREASURY_DISCLAIMER}",
            f"- **OCF/debt (after 4e)**: {cov_a.get('ocf_coverage', '—')}% / {cov_a.get('debt_coverage', '—')}%",
            f"- **treasury precision coverage**: {s4f.get('treasury_precision_coverage_pct', 0)}% · "
            f"**net_cash tickers**: {s4f.get('net_cash_ticker_count', 0)} · "
            f"**NAV proxy (group 1)**: {s4f.get('nav_proxy_coverage_pct', 0)}%",
            f"- **alias fix**: {s4f.get('alias_fix_note', '—')}",
            "- NAV/자사주 지표는 **매수/매도 권고가 아님** — execution authority는 v1.0.2 only",
            "",
        ])

    if hk_manual.get("phase"):
        s4g = hk_manual.get("summary") or {}
        nav_top = hk_manual.get("nav_queue_top5") or []
        blockers = hk_manual.get("top_blockers_sample") or []
        lines.extend([
            "## Hakedaka Manual Verification Queue (shadow only)",
            f"> {MANUAL_VERIFICATION_DISCLAIMER}",
            f"- **treasury precision (event confidence)**: {s4g.get('treasury_event_confidence_coverage_pct', 0)}% · "
            f"**ticker precision**: {s4g.get('treasury_precision_ticker_coverage_pct', 0)}%",
            f"- **NAV manual queue**: {s4g.get('nav_manual_queue_count', 0)}종 · "
            f"**verified top candidates**: {s4g.get('verified_candidate_count', 0)}/"
            f"{s4g.get('top_candidate_count', 0)} · "
            f"**actionable (shadow blocked)**: {s4g.get('actionable_blocked_count', 0)}",
        ])
        if nav_top:
            lines.append("- **NAV queue top 5**:")
            for item in nav_top[:5]:
                lines.append(
                    f"  - {item.get('ticker')} {item.get('name')} "
                    f"(PBR {item.get('current_pbr', '—')}) — {item.get('reason', '')[:80]}"
                )
        if blockers:
            lines.append(f"- **top blockers**: {' | '.join(str(b)[:60] for b in blockers[:3])}")
        lines.extend([
            "- manual verification은 **매수 권고가 아님** — execution authority는 v1.0.2 only",
            "",
        ])

    if hk_catalyst.get("phase"):
        s4h = hk_catalyst.get("summary") or {}
        conf = s4h.get("confidence_distribution") or {}
        lines.extend([
            "## Hakedaka Catalyst Evidence Extraction (shadow only)",
            f"> {CATALYST_EVIDENCE_DISCLAIMER}",
            f"- **documents fetched**: {s4h.get('documents_fetched_ok', 0)} ok · "
            f"{s4h.get('documents_fetch_failed', 0)} failed",
            f"- **extraction confidence**: high {conf.get('high', 0)} · "
            f"medium {conf.get('medium', 0)} · low {conf.get('low', 0)}",
            f"- **treasury precision**: {s4h.get('treasury_precision_before_pct', '—')}% -> "
            f"{s4h.get('treasury_precision_after_pct', '—')}%",
            f"- **manual review remaining**: {s4h.get('shareholder_manual_review_count', 0)} · "
            f"**treasury verified (top15)**: {s4h.get('treasury_verified_top15_count', 0)}",
            "- 촉매 증거는 **매수 권고가 아님** — execution authority는 v1.0.2 only",
            "",
        ])

    if hk_calib.get("phase"):
        s41 = hk_calib.get("summary") or {}
        conf = s41.get("confidence_after") or {}
        reg = s41.get("regression_samples") or {}
        lines.extend([
            "## Hakedaka Catalyst Extraction Calibration (shadow only)",
            f"> {CALIBRATION_DISCLAIMER}",
            f"- **confidence**: high {conf.get('high', 0)} · medium {conf.get('medium', 0)} · "
            f"needs_review {conf.get('needs_review', 0)} · low {conf.get('low', 0)}",
            f"- **parse_suspect**: {s41.get('parse_suspect_count', 0)} · "
            f"**watchlist**: {s41.get('watchlist_count', 0)}종",
            f"- **regression**: 코메론 {reg.get('komeron_017890', {}).get('pass', '—')} · "
            f"신일전자 {reg.get('shinil_002700', {}).get('pass', '—')}",
            "- calibration은 **매수 권고가 아님** — execution authority는 v1.0.2 only",
            "",
        ])

    if hk_forward.get("phase"):
        s4i = hk_forward.get("summary") or {}
        avail = int(s4i.get("available_count") or 0)

        def _fwd(key: str) -> str:
            return fmt_pct(s4i.get(key), na="not available yet") if avail > 0 else "insufficient sample"

        lines.extend([
            "## Hakedaka Forward Return Tracking (shadow only)",
            f"> {FORWARD_RETURN_DISCLAIMER}",
            f"- **추적 종목**: {s4i.get('tracker_count', 0)} · pending {s4i.get('pending_count', 0)} · "
            f"available {avail} · insufficient_price {s4i.get('insufficient_price_count', 0)}",
            f"- **20D avg (top15 / watchlist)**: {_fwd('top15_avg_forward_20d')} / "
            f"{_fwd('watchlist_avg_forward_20d')} · "
            f"5D top15 {_fwd('top15_avg_forward_5d')}",
            f"- **high-confidence catalyst 20D**: {_fwd('high_confidence_avg_forward_20d')} · "
            f"QVM overlap {_fwd('qvm_overlap_avg_forward_20d')}",
            "- 이 섹션은 **shadow diagnostic only** — forward return은 매수/매도 권고가 아님",
            "- 90~120일 데이터가 쌓이기 전까지 실행 판단에 사용하지 않는다",
            "",
        ])

    if hk_forward_qa.get("phase"):
        qa = hk_forward_qa.get("summary") or {}
        lines.extend([
            "## Hakedaka Forward Return QA (shadow only)",
            f"> {FORWARD_RETURN_QA_DISCLAIMER}",
            f"- **signal alignment**: {qa.get('signal_calendar_date', '—')} → "
            f"{qa.get('effective_signal_date', '—')} ({qa.get('signal_date_adjustment_reason', '—')})",
            f"- **last_price_date**: {qa.get('last_price_date', '—')} · "
            f"price_at_signal {qa.get('price_at_signal_filled_count', 0)}/{qa.get('tracker_count', 0)}",
            f"- **status**: pending {qa.get('pending_count', 0)} · available {qa.get('available_count', 0)} · "
            f"signal_price_missing {qa.get('signal_price_missing_count', 0)}",
            "- horizon은 **거래일 기준** — shadow diagnostic only, 실행 판단 금지",
            "",
        ])

    held = alpha.get("holdings_summary") or []
    if held:
        lines.extend([
            "| ticker | weight% | v0.2 | new_buy |",
            "|--------|--------:|------|---------|",
        ])
        for row in held[:8]:
            lines.append(
                f"| {row.get('ticker')} | {row.get('weight_pct', 0)} | "
                f"{row.get('classification')} | {row.get('new_buy_status')} |"
            )
        lines.append("")

    lines.append(f"- **authority**: `{brief.get('execution_authority', EXECUTION_AUTHORITY)}` — 실거래 판단 변경 없음")
    lines.append("")
    return lines


def write_daily_brief(path: Path, brief: dict[str, Any]) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
