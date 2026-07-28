"""P3a — final decision critical path (always executed)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.action_planner import plan_actions
from src.alpha_action_guards import apply_holdings_review_guards
from src.compass.compass_pipeline import CompassPipelineResult
from src.data_loader import write_market_indicators_normalized
from src.data_provenance import audit_market_data_consistency
from src.decision_logger import append_decision_log
from src.final_execution_decision import (
    GROUP_GAP_SOURCE_COMPASS,
    GROUP_GAP_SOURCE_TICKER,
    build_final_execution_decision,
    write_final_execution_decision,
)
from src.models import TriggerStatus
from src.operational_gate import (
    explain_operational_gate,
    gate_from_health_checks,
    health_warn_summaries,
    resolve_operational_gate,
)
from src.portfolio_gap import compute_gaps
from src.regime_classifier import classify_data_gate_from_regime, execution_level_hint, parse_regime
from src.report_writer import (
    write_current_vs_target,
    write_trade_actions,
    write_trigger_alerts,
)
from src.risk_limits import check_risk_limits
from src.trigger_engine import evaluate_triggers, is_buy_trigger_active, is_stop_buy
from src.unified_data_gate import effective_data_gate
from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report
from src.validation.dry_run_log import write_run_manifest
from src.validation.system_health import run_input_health_checks, run_system_health, write_health_report
from src.validators import validate_inputs
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash, normalize_for_semantic_hash

MANIFEST_JSON = "post_decision_artifacts_manifest.json"

FINAL_DECISION_CORE_HASH_KEYS: frozenset[str] = frozenset({
    "data_gate",
    "execution_scope",
    "system_status",
    "operational_verdict",
    "alpha_approval",
    "dry_run_days",
    "execution_permissions",
    "policy_cap",
    "technical_status",
    "operating",
    "alpha_execution_status",
    "group_gap_source",
})


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_final_decision_core_hash(output_dir: Path) -> str:
    """Semantic hash of final_execution_decision.json core fields."""
    path = output_dir / "final_execution_decision.json"
    if not path.exists():
        return "missing"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "invalid"
    subset = {k: doc.get(k) for k in sorted(FINAL_DECISION_CORE_HASH_KEYS) if k in doc}
    normalized = normalize_for_semantic_hash(subset)
    import hashlib

    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()[:16]


def validate_final_decision_safety(output_dir: Path, data_dir: Path) -> dict[str, Any]:
    """Re-validate safety invariants without changing decision logic."""
    from src.alpha.target_portfolio_guard import user_target_portfolio_path
    from src.alpha.target_write_audit import get_last_target_write_audit
    from src.report.authoritative_status import resolve_authoritative_execution
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json
    from src.validation.system_health import run_input_health_checks

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    actual_buy = int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)
    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc)
    audit = get_last_target_write_audit(output_dir)
    target_writes = int(audit.get("target_write_count") or 0) if audit else 0

    as_of = str(final_doc.get("as_of") or "")
    health = run_input_health_checks(data_dir, as_of=as_of or None, output_dir=output_dir)
    guard = next((c for c in health.checks if c.name == "target_portfolio_guard"), None)
    guard_status = str(guard.status if guard else "unknown")

    return {
        "actual_buy_allowed": actual_buy,
        "target_write_count": target_writes,
        "target_guard_status": guard_status,
        "authoritative_execution_scope": str(auth.get("execution_scope") or ""),
        "authoritative_data_gate": str(auth.get("unified_data_gate") or ""),
        "final_decision_present": bool(final_doc),
    }


def build_gate_notes(input_health: Any, alpha_data_gate: str | None, execution_scope: str) -> list[str]:
    notes: list[str] = []
    for check in input_health.checks:
        if check.name == "prices_coverage":
            notes.append(check.message)
            break
    if alpha_data_gate:
        notes.append(f"Alpha 재무 PIT gate: {alpha_data_gate}")
    notes.append(f"Execution scope: {execution_scope}")
    return notes


def patch_compass_regime_gate(
    output_dir: Path,
    data_gate: str,
    execution_level: int,
    execution_scope: str | None = None,
) -> None:
    path = output_dir / "compass_regime.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["data_gate"] = data_gate
    data["execution_level"] = execution_level
    if execution_scope:
        data["execution_scope"] = execution_scope
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_gpt_context_gate(
    output_dir: Path,
    *,
    executable_gate: str,
    policy_gate: str,
    health_gate: str,
    portfolio_gate: str,
    alpha_data_gate: str | None,
    execution_scope: str,
    alpha_trade_permission: str,
    alpha_position_action: str,
) -> None:
    path = output_dir / "gpt_context.json"
    if not path.exists():
        return
    ctx = json.loads(path.read_text(encoding="utf-8"))
    ctx["compass_base_gate"] = portfolio_gate
    ctx["portfolio_gate"] = portfolio_gate
    ctx["policy_gate"] = policy_gate
    ctx["alpha_data_gate"] = alpha_data_gate or ctx.get("alpha_data_gate")
    ctx["health_gate"] = health_gate
    ctx["execution_data_gate"] = executable_gate
    ctx["data_gate"] = executable_gate
    ctx["execution_scope"] = execution_scope
    ctx["alpha_trade_permission"] = alpha_trade_permission
    ctx["alpha_position_action"] = alpha_position_action
    if isinstance(ctx.get("regime"), dict):
        reg = ctx["regime"]
        if "data_gate" in reg and "compass_base_gate" not in reg:
            reg["compass_base_gate"] = reg.pop("data_gate")
        reg["execution_data_gate"] = executable_gate
    ctx["executable_actions_note"] = (
        "execution_data_gate=최종 실행 게이트 · compass_base_gate=나침반/포트폴리오 기준 · "
        "alpha_data_gate=알파 재무 PIT · "
        + (
            "kr_alpha=리스크 축소 Trim만 Executable (RISK_REDUCE_ONLY)"
            if alpha_position_action == "RISK_REDUCE_ONLY"
            else "kr_alpha=ETF_ONLY 시 Review-only/theoretical"
        )
    )
    path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class FinalDecisionCoreInputs:
    data_dir: Path
    output_dir: Path
    run_id: str
    positions: list[Any]
    targets: list[Any]
    market: Any
    market_bundle: Any
    policy: dict[str, Any]
    rules: Any
    compass_result: CompassPipelineResult | None
    alpha_out: Any | None
    alpha_gate: str | None
    alpha_count: int
    generated_targets: list[Any] | None
    profile: str | None = None


@dataclass
class FinalDecisionCoreResult:
    run_id: str
    data_gate: str
    execution_level: int
    exec_level: int
    action_count: int
    alpha_count: int
    final_decision: Any
    final_doc: dict[str, Any]
    actions: list[Any]
    review_actions: list[Any]
    theoretical_actions: list[Any]
    gap_rows: list[Any]
    alerts: list[Any]
    market: Any
    compass_result: CompassPipelineResult | None
    alpha_out: Any | None
    alpha_gate: str | None
    generated_targets: list[Any] | None
    targets: list[Any]
    acceptance: Any
    health_report: Any
    operational_status: str
    policy_cap_result: Any
    throttle_meta: dict[str, Any]
    dry_run_days: int
    dry_run_required: int
    applied_regime: str | None
    computed_regime: str | None
    override_active: bool
    trigger_active: list[str]
    buy_allowed: int
    kr_alpha_wait: int
    alpha_approval: str
    policy_gate: str
    health_gate: str
    portfolio_gate: str
    alpha_trade_permission: str
    alpha_position_action: str
    hard_stops_detail: dict[str, Any]
    gate_notes: list[str]
    target_guard_severity: str
    core_hash: str = ""
    trigger_group_gaps: Any = None
    core_price_status: str = "pass"


def run_final_decision_core(inputs: FinalDecisionCoreInputs) -> FinalDecisionCoreResult:
    """Execute the critical final decision path — always runs."""
    data_dir = inputs.data_dir
    output_dir = inputs.output_dir
    positions = inputs.positions
    targets = inputs.targets
    market = inputs.market
    market_bundle = inputs.market_bundle
    policy = inputs.policy
    rules = inputs.rules
    compass_result = inputs.compass_result
    alpha_out = inputs.alpha_out
    alpha_gate = inputs.alpha_gate
    alpha_count = inputs.alpha_count
    generated_targets = inputs.generated_targets
    run_id = inputs.run_id
    profile = inputs.profile

    validation = validate_inputs(positions, targets, policy)
    portfolio_gate = classify_data_gate_from_regime(market.regime, validation.data_gate)
    gate_policy = policy.get("data_gate_policy", {})
    merge_alpha = bool(gate_policy.get("merge_alpha_gate", True))

    input_health = run_input_health_checks(data_dir, as_of=market.date, output_dir=output_dir)
    health_gate = gate_from_health_checks(input_health.checks)

    from src.validation.tier_a_price_coverage import (
        alpha_gate_from_health_detail,
        apply_alpha_price_gate_to_data_gate,
    )

    alpha_price_check = next(
        (c for c in input_health.checks if c.name == "alpha_price_gate"), None,
    )
    if alpha_price_check and alpha_gate and alpha_price_check.detail:
        alpha_gate = apply_alpha_price_gate_to_data_gate(
            alpha_gate,
            alpha_gate_from_health_detail(alpha_price_check.detail),
        )

    policy_gate = effective_data_gate(portfolio_gate, alpha_gate, merge_alpha=merge_alpha)
    data_gate = resolve_operational_gate(
        portfolio_gate, alpha_gate, health_gate, merge_alpha=merge_alpha
    )

    from src.execution_scope import (
        apply_execution_scope_to_actions,
        count_dry_run_days,
        derive_alpha_approval,
        derive_alpha_permissions,
        derive_execution_scope,
    )

    dry_run_days = count_dry_run_days(output_dir)
    dry_run_required = 10
    for chk in input_health.checks:
        if chk.name == "dry_run":
            dry_run_required = int(getattr(chk, "required", None) or 10)
            break
    technical_scope = derive_execution_scope(
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        alpha_data_gate=alpha_gate,
        health_gate=health_gate,
        dry_run_days=dry_run_days,
    )
    from src.policy_cap import build_technical_status_block, resolve_policy_cap

    computed_for_cap: str | None = None
    if compass_result is not None and getattr(compass_result, "compass", None) is not None:
        computed_for_cap = getattr(compass_result.compass, "computed_regime", None)
        if computed_for_cap is not None and hasattr(computed_for_cap, "value"):
            computed_for_cap = computed_for_cap.value
        computed_for_cap = str(computed_for_cap) if computed_for_cap else None
    if not computed_for_cap:
        regime_path_early = output_dir / "compass_regime.json"
        if regime_path_early.exists():
            try:
                computed_for_cap = (
                    json.loads(regime_path_early.read_text(encoding="utf-8")).get("computed_regime")
                )
            except Exception:
                computed_for_cap = None

    policy_cap_result = resolve_policy_cap(
        market,
        technical_scope=technical_scope,
        data_gate=data_gate,
        health_gate=health_gate,
        computed_regime=str(computed_for_cap) if computed_for_cap else None,
    )
    execution_scope = policy_cap_result.capped_execution_scope  # type: ignore[assignment]
    technical_status_block = build_technical_status_block(
        data_gate=data_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        alpha_gate=alpha_gate,
        execution_scope=technical_scope,
    )
    execution_policy = policy.get("execution_policy", {})
    alpha_trade_permission, alpha_position_action = derive_alpha_permissions(
        alpha_data_gate=alpha_gate,
        execution_scope=execution_scope,
        execution_policy=execution_policy,
    )
    if alpha_price_check and alpha_price_check.detail:
        from src.operational_gate import apply_alpha_price_action_to_permissions

        alpha_trade_permission, alpha_position_action = apply_alpha_price_action_to_permissions(
            str(alpha_price_check.detail.get("action", "ALPHA_OK")),
            alpha_trade_permission,
            alpha_position_action,
        )
    target_guard_chk = next(
        (c for c in input_health.checks if c.name == "target_portfolio_guard"), None,
    )
    target_guard_severity = str(
        (target_guard_chk.detail or {}).get("severity", "PASS") if target_guard_chk else "PASS"
    )
    if target_guard_severity == "FAIL":
        from src.alpha.target_portfolio_guard import apply_target_guard_to_permissions

        alpha_trade_permission, alpha_position_action = apply_target_guard_to_permissions(
            alpha_trade_permission,
            alpha_position_action,
            guard_severity=target_guard_severity,
        )
    alpha_approval = derive_alpha_approval(alpha_gate, execution_scope)

    gap_rows = compute_gaps(positions, targets)
    risk = check_risk_limits(positions, gap_rows, policy)
    growth_score = compass_result.compass.growth_score if compass_result else None

    from src.compass.compass_pipeline import write_portfolio_actions_md, write_portfolio_gap_csv
    from src.compass.group_action_planner import plan_group_actions
    from src.compass.group_gap import compute_group_gaps, group_gap_rows_to_trigger_map
    from src.portfolio_gap import aggregate_by_asset_group

    raw_group_gaps = None
    group_gap_source = GROUP_GAP_SOURCE_TICKER
    if compass_result:
        raw_group_gaps = compute_group_gaps(positions, compass_result.allocation)
        group_gap_source = GROUP_GAP_SOURCE_COMPASS
        trigger_group_gaps = group_gap_rows_to_trigger_map(raw_group_gaps)
    else:
        trigger_group_gaps = aggregate_by_asset_group(gap_rows)

    core_price_status = str(core_chk.status if (core_chk := next(
        (c for c in input_health.checks if c.name == "core_price_gate"), None
    )) else "pass")

    alerts = evaluate_triggers(
        market,
        rules,
        asset_group_gaps=trigger_group_gaps,
        gap_rows=gap_rows,
        growth_score=growth_score,
        data_dir=data_dir,
        core_price_gate=core_price_status,
        data_gate=data_gate,
        health_gate=health_gate,
        dry_run_days=dry_run_days,
    )

    buy_trigger_groups = [
        "domestic_beta", "global_beta", "hedge_alt", "fx_dollar", "income_alt", "cash_short_bond",
    ]
    any_buy_trigger = any(is_buy_trigger_active(alerts, g) for g in buy_trigger_groups)
    stop_buy = is_stop_buy(alerts)
    gate_explanation = explain_operational_gate(
        portfolio_gate,
        alpha_gate,
        health_gate,
        merge_alpha=merge_alpha,
        health_warns=health_warn_summaries(input_health.checks),
    )
    market_audit = audit_market_data_consistency(data_dir)

    updated_group_gaps = None
    if raw_group_gaps is not None and compass_result:
        updated_group_gaps = plan_group_actions(
            raw_group_gaps,
            applied_regime=compass_result.compass.applied_regime,
            data_gate=data_gate,
            buy_triggers_active=any_buy_trigger,
            execution_scope=execution_scope,
            stop_buy=stop_buy,
        )

    group_action_map = (
        {g.asset_group: g.action for g in updated_group_gaps}
        if updated_group_gaps
        else {}
    )
    plan_kw = dict(
        group_actions=group_action_map,
        buy_triggers_active=any_buy_trigger,
        execution_scope=execution_scope,
        execution_policy=execution_policy,
    )
    holdings_review_dicts: list[dict] = []
    if alpha_out is not None:
        holdings_review_dicts = [h.model_dump() for h in alpha_out.result.holdings_review]

    theoretical_actions = plan_actions(
        gap_rows, alerts, risk, policy_gate, rules, **plan_kw
    )
    raw_actions = apply_holdings_review_guards(
        plan_actions(gap_rows, alerts, risk, data_gate, rules, **plan_kw),
        gap_rows,
        holdings_review_dicts,
    )
    actions, review_actions = apply_execution_scope_to_actions(
        raw_actions, gap_rows, execution_scope,
        execution_policy=execution_policy,
    )
    if target_guard_severity == "FAIL":
        from src.alpha.target_portfolio_guard import apply_target_guard_to_actions

        actions, tg_review = apply_target_guard_to_actions(
            actions, gap_rows, guard_severity=target_guard_severity,
        )
        review_actions.extend(tg_review)

    from src.exposure.core_deployment_throttle import (
        apply_core_deployment_throttle,
        build_ar1_parity_check,
        write_ar1_parity_check,
        write_core_deployment_throttle_status,
    )

    actions, throttle_meta = apply_core_deployment_throttle(
        actions,
        gap_rows,
        data_dir=data_dir,
        output_dir=output_dir,
        data_gate=data_gate,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        as_of=market.date,
    )
    write_core_deployment_throttle_status(output_dir, throttle_meta)
    ar1_parity = build_ar1_parity_check(
        data_dir,
        output_dir,
        actions=actions,
        gap_rows=gap_rows,
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        throttle_meta=throttle_meta,
    )
    write_ar1_parity_check(output_dir, ar1_parity)

    regime_info = parse_regime(market)
    max_gap = max((abs(r.gap) for r in gap_rows), default=0)
    exec_level = execution_level_hint(data_gate, regime_info, max_gap)

    gate_notes = build_gate_notes(input_health, alpha_gate, execution_scope)

    from src.execution_guards import build_hard_stops_detail

    hard_stops_detail = build_hard_stops_detail(
        risk,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_market_indicators_normalized(
        market_bundle, output_dir / "market_indicators_normalized.json"
    )
    if updated_group_gaps:
        write_portfolio_gap_csv(updated_group_gaps, output_dir / "portfolio_gap.csv")
        write_portfolio_actions_md(updated_group_gaps, output_dir / "portfolio_actions.md")

    write_current_vs_target(gap_rows, output_dir / "current_vs_target.csv")
    write_trade_actions(actions, output_dir / "trade_actions.csv")
    write_trade_actions(theoretical_actions, output_dir / "theoretical_trade_actions.csv")
    if review_actions:
        write_trade_actions(review_actions, output_dir / "kr_alpha_review_actions.csv")
    write_trigger_alerts(
        output_dir / "trigger_alerts.md",
        alerts,
        actions,
        review_actions=review_actions,
        execution_scope=execution_scope,
        gap_rows=gap_rows,
        asset_group_gaps=trigger_group_gaps,
        data_gate=data_gate,
        dry_run_days=dry_run_days,
        alpha_position_action=alpha_position_action,
        execution_policy=execution_policy,
    )
    from src.trigger_reviews import build_kospi_trigger_reviews, write_trigger_reviews

    trigger_reviews = build_kospi_trigger_reviews(
        market,
        rules,
        core_price_gate=core_price_status,
        data_gate=data_gate,
        health_gate=health_gate,
        dry_run_days=dry_run_days,
    )
    write_trigger_reviews(output_dir / "trigger_reviews.json", trigger_reviews, as_of=market.date)
    append_decision_log(
        output_dir / "decision_log.jsonl",
        {
            "data_gate": data_gate,
            "policy_gate": policy_gate,
            "health_gate": health_gate,
            "portfolio_gate": portfolio_gate,
            "alpha_data_gate": alpha_gate,
            "alpha_gate": alpha_gate,
            "data_gate_detail": gate_explanation,
            "market_data_audit": market_audit,
            "alpha_trade_permission": alpha_trade_permission,
            "alpha_position_action": alpha_position_action,
            "alpha_approval": alpha_approval,
            "execution_scope": execution_scope,
            "technical_execution_scope": technical_scope,
            "policy_cap": policy_cap_result.to_dict(),
            "regime": market.regime,
            "execution_level": exec_level,
            "action_count": len(actions),
            "theoretical_action_count": len(theoretical_actions),
            "review_action_count": len(review_actions),
            "hard_stops": hard_stops_detail["risk_hard_stop_count"],
            "hard_stops_detail": hard_stops_detail,
            "validation_errors": validation.errors,
            "health_overall": input_health.overall,
            "health_fail_count": input_health.summary.get("fail", 0),
            "used_generated_target": bool(compass_result and compass_result.generated_targets),
            "tier2_used": compass_result.tier2_used if compass_result else False,
        },
    )
    patch_compass_regime_gate(output_dir, data_gate, exec_level, execution_scope)
    patch_gpt_context_gate(
        output_dir,
        executable_gate=data_gate,
        policy_gate=policy_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        alpha_data_gate=alpha_gate,
        execution_scope=execution_scope,
        alpha_trade_permission=alpha_trade_permission,
        alpha_position_action=alpha_position_action,
    )
    if compass_result:
        from src.compass.compass_report import write_compass_report

        patched_compass = compass_result.compass.model_copy(
            update={"data_gate": data_gate, "execution_level": exec_level}
        )
        write_compass_report(
            output_dir / "compass_report.md",
            patched_compass,
            compass_result.allocation,
            group_gaps=updated_group_gaps or compass_result.group_gaps,
            mismatch_warnings=compass_result.mismatch_warnings,
            generated_targets=compass_result.generated_targets,
            tier2_used=compass_result.tier2_used,
        )
    applied_regime = computed_regime = None
    override_active = False
    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        reg = json.loads(regime_path.read_text(encoding="utf-8"))
        applied_regime = reg.get("applied_regime")
        computed_regime = reg.get("computed_regime")
        override_active = bool((reg.get("override") or {}).get("active"))

    trigger_active = [a.key for a in alerts if a.status == TriggerStatus.ACTIVE]
    buy_allowed = sum(1 for a in actions if a.action == "Buy-allowed")
    kr_alpha_wait = sum(
        1 for a in actions
        if a.action == "Wait" and any(r.ticker == a.ticker and r.asset_group == "kr_alpha" for r in gap_rows)
    )

    write_run_manifest(
        output_dir,
        run_id=run_id,
        as_of=market.date,
        source_outputs=[
            "final_execution_decision.json",
            "market_indicators_normalized.json",
            "compass_regime.json",
            "system_health.json",
            "acceptance_report.json",
            "trade_actions.csv",
            "executable_brief.md",
            "gpt_context.json",
            "decision_log.jsonl",
            "ai_export_bundle.json",
            "alpha_execution_status.json",
            "shadow_diagnostic.json",
            "ops_shadow_log.csv",
            "alpha_v0_2_classification.csv",
            "alpha_v0_2_shadow.json",
            "alpha_v0_2_shadow_log.csv",
            "alpha_v2_universe.csv",
            "alpha_v2_scored.csv",
            "alpha_v2_top30.csv",
            "alpha_v2_final_candidates.csv",
            "alpha_v2_flow_triggers.csv",
            "alpha_v2_profit_sweep_candidates.csv",
            "alpha_v2_summary.json",
            "daily_brief.json",
            "daily_report.md",
            "saa_restart_readiness_report.json",
            "saa_restart_readiness_report.md",
            "report_clarity_validation.json",
            "core_saa_reference_diagnostic.json",
            "alpha_performance_dashboard.json",
            "alpha_performance_dashboard.csv",
            "alpha_gate_opportunity_cost.csv",
            "alpha_grade_forward_return.csv",
            "portfolio_nav_log.csv",
            "hakedaka_primary_hunt_list.csv",
            "hakedaka_catalyst_scores.csv",
            "hakedaka_group_forward_return.csv",
            "hakedaka_qvm_overlap.csv",
            "hakedaka_rerating_shadow.json",
            "hakedaka_preliminary_hunt_list.csv",
            "hakedaka_data_quality_report.json",
            "hakedaka_data_quality_report.csv",
            "hakedaka_dart_events.csv",
            "data/hakedaka_fundamentals.csv",
        ],
    )
    health_report = run_system_health(data_dir, output_dir)
    write_health_report(health_report, output_dir / "system_health.json")

    acceptance = run_acceptance_check(data_dir, output_dir)
    write_acceptance_report(acceptance, output_dir / "acceptance_report.json")

    from src.alpha.gate_stamp import build_alpha_execution_status, write_alpha_gate_stamp

    alpha_status = build_alpha_execution_status(
        data_gate=data_gate,
        alpha_data_gate=alpha_gate,
        execution_scope=execution_scope,
        alpha_trade_permission=alpha_trade_permission,
        alpha_position_action=alpha_position_action,
    )
    write_alpha_gate_stamp(output_dir, alpha_status)

    from src.alpha.target_draft_bridge import default_target_draft_path, is_target_draft_pending
    from src.operating_state import derive_operating_state
    from src.policy_cap import apply_policy_cap_to_approval

    operational_status = apply_policy_cap_to_approval(acceptance.overall, policy_cap_result)

    draft_path = default_target_draft_path()
    operating_bundle = derive_operating_state(
        system_status=operational_status,
        data_gate=data_gate,
        execution_scope=execution_scope,
        alpha_approval=alpha_approval,
        dry_run_days=acceptance.dry_run_days,
        executable_actions=actions,
        review_actions=review_actions,
        gap_rows=gap_rows,
        group_gaps=updated_group_gaps,
        health_checks=input_health.checks,
        target_draft_pending=draft_path.exists() and is_target_draft_pending(data_dir, draft_path),
        buy_triggers_active=any_buy_trigger,
        theoretical_actions=theoretical_actions,
    )

    from src.execution_permissions import build_execution_permissions

    core_chk = next((c for c in input_health.checks if c.name == "core_price_gate"), None)
    alpha_price_chk = next((c for c in input_health.checks if c.name == "alpha_price_gate"), None)
    alpha_price_action = str(
        (alpha_price_chk.detail or {}).get("action", "ALPHA_OK") if alpha_price_chk else "ALPHA_OK"
    )
    execution_permissions = build_execution_permissions(
        execution_scope=execution_scope,
        alpha_trade_permission=alpha_trade_permission,
        alpha_position_action=alpha_position_action,
        alpha_price_action=alpha_price_action,
        restricted_modes=list(input_health.meta.get("restricted_modes") or []),
        health_gate=health_gate,
        core_price_gate_status=str(core_chk.status if core_chk else "pass"),
        alpha_price_gate_status=str(alpha_price_chk.status if alpha_price_chk else "pass"),
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        alpha_gate=alpha_gate or "GREEN",
        policy_cap_active=policy_cap_result.active,
        max_operational_approval=policy_cap_result.max_operational_approval,
        cap_regime=policy_cap_result.cap_regime,
        target_guard_severity=target_guard_severity,
    )

    final_decision = build_final_execution_decision(
        run_id=run_id,
        as_of=market.date,
        system_status=operational_status,
        data_gate=data_gate,
        execution_scope=execution_scope,
        alpha_approval=alpha_approval,
        alpha_execution_status=alpha_status["alpha_execution_status"],
        group_gap_source=group_gap_source,
        operational_verdict=acceptance.operational_verdict,
        dry_run_days=acceptance.dry_run_days,
        executable_actions=actions,
        review_actions=review_actions,
        group_gaps=updated_group_gaps,
        data_gate_detail=gate_explanation,
        market_data_audit=market_audit,
        execution_permissions=execution_permissions,
        policy_cap=policy_cap_result.to_dict(),
        technical_status=technical_status_block,
        operating=operating_bundle,
    )
    from src.validation.fail_soft_pipeline import (
        patch_gpt_context_fail_soft,
        refresh_fail_soft_after_final,
    )

    final_doc = refresh_fail_soft_after_final(
        final_decision.to_dict(),
        output_dir=output_dir,
        data_dir=data_dir,
        alpha_data_gate=alpha_gate,
        candidate_count=alpha_count,
        dry_run_days=acceptance.dry_run_days,
        dry_run_required=dry_run_required,
        policy_cap_active=policy_cap_result.active,
    )
    final_decision.execution_permissions = final_doc.get("execution_permissions")
    write_final_execution_decision(final_decision, output_dir / "final_execution_decision.json")
    patch_gpt_context_fail_soft(output_dir, final_doc.get("execution_permissions") or {})

    core_hash = compute_final_decision_core_hash(output_dir)
    validate_final_decision_safety(output_dir, data_dir)

    return FinalDecisionCoreResult(
        run_id=run_id,
        data_gate=data_gate,
        execution_level=exec_level,
        exec_level=exec_level,
        action_count=len(actions),
        alpha_count=alpha_count,
        final_decision=final_decision,
        final_doc=final_doc,
        actions=actions,
        review_actions=review_actions,
        theoretical_actions=theoretical_actions,
        gap_rows=gap_rows,
        alerts=alerts,
        market=market,
        compass_result=compass_result,
        alpha_out=alpha_out,
        alpha_gate=alpha_gate,
        generated_targets=generated_targets,
        targets=targets,
        acceptance=acceptance,
        health_report=health_report,
        operational_status=operational_status,
        policy_cap_result=policy_cap_result,
        throttle_meta=throttle_meta,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        applied_regime=applied_regime,
        computed_regime=computed_regime,
        override_active=override_active,
        trigger_active=trigger_active,
        buy_allowed=buy_allowed,
        kr_alpha_wait=kr_alpha_wait,
        alpha_approval=alpha_approval,
        policy_gate=policy_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        alpha_trade_permission=alpha_trade_permission,
        alpha_position_action=alpha_position_action,
        hard_stops_detail=hard_stops_detail,
        gate_notes=gate_notes,
        target_guard_severity=target_guard_severity,
        core_hash=core_hash,
        trigger_group_gaps=trigger_group_gaps,
        core_price_status=core_price_status,
    )
