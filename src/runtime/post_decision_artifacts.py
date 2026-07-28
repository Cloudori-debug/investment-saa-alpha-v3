"""P3a — post-decision heavy artifacts with cache-first skip."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.exposure.absolute_return_policy import write_absolute_return_status
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash
from src.runtime.final_decision_core import (
    MANIFEST_JSON,
    FinalDecisionCoreResult,
    compute_final_decision_core_hash,
    validate_final_decision_safety,
)

REQUIRED_ARTIFACT_OUTPUTS: tuple[str, ...] = (
    "shadow_diagnostic.json",
    "output_cross_validation.json",
    "executable_brief.md",
    "exposure_lookthrough.json",
)

ALLOWED_CACHE_SKIP_REASONS: frozenset[str] = frozenset({
    "inputs_unchanged",
    "artifacts_present",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _report_inputs_hash(data_dir: Path, output_dir: Path) -> str:
    parts = [
        compute_semantic_file_hash(output_dir / "trade_actions.csv"),
        compute_semantic_file_hash(output_dir / "acceptance_report.json"),
        compute_semantic_file_hash(output_dir / "system_health.json"),
        compute_semantic_file_hash(data_dir / "portfolio_policy.yaml"),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def compute_post_decision_input_hash(data_dir: Path, output_dir: Path) -> dict[str, str]:
    from src.alpha.target_portfolio_guard import user_target_portfolio_path

    user_target = user_target_portfolio_path(data_dir)
    return {
        "final_decision_core_hash": compute_final_decision_core_hash(output_dir),
        "alpha_v2_summary_hash": compute_semantic_file_hash(output_dir / "alpha_v2_summary.json"),
        "flow_dashboard_summary_hash": compute_semantic_file_hash(output_dir / "flow_dashboard_summary.json"),
        "target_portfolio_hash": compute_semantic_file_hash(data_dir / "target_portfolio.csv"),
        "user_target_hash": compute_semantic_file_hash(user_target),
        "report_inputs_hash": _report_inputs_hash(data_dir, output_dir),
    }


def _combined_input_hash(hashes: dict[str, str]) -> str:
    payload = {k: hashes[k] for k in sorted(hashes)}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _artifacts_present(output_dir: Path) -> tuple[bool, list[str]]:
    missing = [name for name in REQUIRED_ARTIFACT_OUTPUTS if not (output_dir / name).exists()]
    return not missing, missing


def load_post_decision_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_post_decision_manifest(output_dir: Path, doc: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_JSON
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_post_decision_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str = "standard",
    force_refresh: bool = False,
) -> dict[str, Any]:
    hashes = compute_post_decision_input_hash(data_dir, output_dir)
    combined = _combined_input_hash(hashes)
    prev = load_post_decision_manifest(output_dir)
    prev_combined = str(prev.get("combined_input_hash") or "")
    outputs_ok, missing = _artifacts_present(output_dir)
    hash_match = bool(prev_combined and prev_combined == combined)
    blockers: list[str] = []
    mode = str(run_mode).lower()

    if mode == "deep" and force_refresh:
        cache_hit = False
        reason = "deep_force_refresh"
    elif mode == "quick":
        cache_hit = outputs_ok
        reason = "quick_cache_only" if cache_hit else "quick_outputs_missing"
    elif not outputs_ok:
        cache_hit = False
        reason = "required_outputs_missing"
        blockers.append("artifacts_missing")
        if missing:
            blockers.append(f"missing:{','.join(missing[:4])}")
    elif not hash_match:
        cache_hit = False
        reason = "input_hash_changed"
        blockers.append("combined_hash_changed")
    else:
        cache_hit = True
        reason = "inputs_unchanged"

    return {
        "cache_hit": cache_hit,
        "skip_reason": reason,
        "combined_input_hash": combined,
        "combined_input_hash_previous": prev_combined,
        "hash_match": hash_match,
        "outputs_present": outputs_ok,
        "missing_outputs": missing,
        "blockers": blockers,
        "input_hashes": hashes,
        "run_mode": mode,
    }


def _load_exposure_report(output_dir: Path) -> Any:
    path = output_dir / "exposure_lookthrough.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class PostDecisionArtifactsResult:
    cache_hit: bool = False
    reused: bool = False
    recomputed: list[str] = field(default_factory=list)
    skip_reason: str = ""
    elapsed_seconds: float = 0.0
    exposure_report: Any = None
    alpha_backtest_ran: bool = False
    combined_input_hash: str = ""
    safety: dict[str, Any] = field(default_factory=dict)


def run_post_decision_artifacts(
    core: FinalDecisionCoreResult,
    *,
    data_dir: Path,
    output_dir: Path,
    profile: str | None,
    run_backtest: bool,
    run_alpha_backtest: bool,
    rules: Any,
    positions: list[Any],
) -> PostDecisionArtifactsResult:
    """Generate heavy post-decision artifacts (no cache)."""
    run_id = core.run_id
    market = core.market
    final_doc = core.final_doc
    final_decision = core.final_decision
    alpha_out = core.alpha_out
    alpha_gate = core.alpha_gate
    alpha_count = core.alpha_count
    generated_targets = core.generated_targets
    targets = core.targets
    compass_result = core.compass_result
    data_gate = core.data_gate
    execution_scope = core.final_decision.execution_scope
    alpha_trade_permission = core.alpha_trade_permission
    alpha_position_action = core.alpha_position_action
    gate_notes = core.gate_notes
    gap_rows = core.gap_rows
    alerts = core.alerts
    actions = core.actions
    theoretical_actions = core.theoretical_actions
    acceptance = core.acceptance
    policy_cap_result = core.policy_cap_result
    operational_status = core.operational_status
    applied_regime = core.applied_regime
    portfolio_gate = core.portfolio_gate
    health_gate = core.health_gate
    alpha_approval = core.alpha_approval
    buy_allowed = core.buy_allowed
    kr_alpha_wait = core.kr_alpha_wait
    trigger_active = core.trigger_active
    computed_regime = core.computed_regime
    override_active = core.override_active
    throttle_meta = core.throttle_meta
    dry_run_days = core.dry_run_days
    dry_run_required = core.dry_run_required
    trigger_group_gaps = core.trigger_group_gaps
    core_price_status = core.core_price_status

    from src.alpha.alpha_pipeline import refresh_alpha_signal_board_from_outputs

    perms = final_doc.get("execution_permissions") or {}
    refresh_alpha_signal_board_from_outputs(
        data_dir,
        output_dir,
        alpha_auto_buy_permission=str(perms.get("alpha_auto_buy_permission", "BLOCKED")),
    )

    if alpha_out is not None:
        from src.alpha.alpha_report import write_alpha_report
        from src.alpha.alpha_signal_board import load_signal_board_from_csv

        write_alpha_report(
            output_dir / "alpha_report.md",
            alpha_out.result,
            executable_gate=data_gate,
            alpha_data_gate=alpha_gate,
            execution_scope=execution_scope,
            alpha_trade_permission=alpha_trade_permission,
            alpha_position_action=alpha_position_action,
            gate_notes=gate_notes,
            signal_rows=load_signal_board_from_csv(output_dir / "alpha_signal_board.csv"),
            alpha_sector_data_gate=str(
                (alpha_out.gpt_context.get("shortlist_meta") or {}).get("alpha_sector_data_gate", "GREEN")
            ),
            top10_candidate_meta=(alpha_out.gpt_context.get("kr_alpha_meta") or {}).get("top10_sector_candidate"),
            flow_refresh_meta=(alpha_out.gpt_context.get("kr_alpha_meta") or {}).get("flow_refresh"),
        )

    from src.alpha.target_portfolio_proposal import (
        ensure_user_target_snapshot,
        write_target_diff_review,
        write_target_portfolio_proposal,
    )
    from src.alpha.target_portfolio_guard import write_target_guard_diff

    write_target_portfolio_proposal(
        generated_targets or targets,
        output_dir,
        source="compass_pipeline" if compass_result else "template",
    )
    ensure_user_target_snapshot(data_dir, output_dir)
    write_target_diff_review(data_dir, output_dir)
    write_target_guard_diff(data_dir, output_dir)

    from src.validation.fail_soft_pipeline import write_fail_soft_artifacts as _write_vf

    cross_val_path = output_dir / "output_cross_validation.json"
    _cross_early = None
    if cross_val_path.exists():
        _cross_early = json.loads(cross_val_path.read_text(encoding="utf-8"))
    _write_vf(
        output_dir=output_dir,
        data_dir=data_dir,
        run_id=run_id,
        as_of=market.date,
        final_decision=final_decision.to_dict(),
        clarity=None,
        cross_val=_cross_early,
    )

    from src.decision.shadow_diagnostic import (
        append_ops_shadow_log,
        build_shadow_diagnostic,
        write_shadow_diagnostic,
    )

    core_price_status = core.core_price_status
    shadow_doc = build_shadow_diagnostic(
        run_id=run_id,
        as_of=market.date,
        market=market,
        positions=positions,
        gap_rows=gap_rows,
        alerts=alerts,
        actions=actions,
        theoretical_actions=theoretical_actions,
        rules=rules,
        data_gate=data_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        alpha_gate=alpha_gate,
        execution_scope=execution_scope,
        core_price_gate=core_price_status,
        dry_run_days=acceptance.dry_run_days,
        policy_cap=policy_cap_result.to_dict(),
        alpha_trade_permission=alpha_trade_permission,
        operational_status=operational_status,
        allocation_groups=compass_result.allocation.groups if compass_result else None,
        applied_regime=applied_regime,
        saa_profile=compass_result.allocation.profile if compass_result else profile,
        data_dir=data_dir,
        shadow_log_path=output_dir / "ops_shadow_log.csv",
        targets=targets,
        asset_group_gaps=trigger_group_gaps,
    )
    write_shadow_diagnostic(output_dir / "shadow_diagnostic.json", shadow_doc)
    append_ops_shadow_log(output_dir / "ops_shadow_log.csv", shadow_doc)
    from src.decision.shadow_performance import enrich_ops_shadow_log_retrospective

    enrich_ops_shadow_log_retrospective(output_dir / "ops_shadow_log.csv", data_dir)

    from src.validation.output_cross_validation import (
        validate_outputs_cross_check,
        write_cross_validation_report,
    )

    cross_val = validate_outputs_cross_check(output_dir)
    write_cross_validation_report(cross_val, output_dir / "output_cross_validation.json")

    from src.operational_checklist import write_executable_brief

    write_executable_brief(data_dir, output_dir)

    stale_max = None
    prov_path = data_dir / "market_data_provenance.json"
    if prov_path.exists():
        fields = (json.loads(prov_path.read_text(encoding="utf-8")).get("fields") or {})
        if fields:
            stale_max = max(int(v.get("stale_business_days", 0)) for v in fields.values())

    override_age = None
    if getattr(market, "regime_set_date", None):
        from src.data_refresh.external_market import business_days_between
        override_age = business_days_between(market.regime_set_date, market.date)

    from src.validation.dry_run_log import append_dry_run_log

    append_dry_run_log(
        output_dir,
        run_id=run_id,
        as_of=market.date,
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        alpha_gate=alpha_gate,
        applied_regime=applied_regime,
        computed_regime=computed_regime,
        override_active=override_active,
        action_count=len(actions),
        alpha_candidate_count=alpha_count,
        trigger_active=trigger_active,
        overall_status=acceptance.overall,
        execution_scope=execution_scope,
        alpha_approval=alpha_approval,
        buy_allowed_count=buy_allowed,
        kr_alpha_wait_count=kr_alpha_wait,
        market_stale_max_days=stale_max,
        override_age_days=override_age,
    )

    if run_backtest and (data_dir / "market_indicators_history.csv").exists():
        from src.backtest.regime_backtest import run_regime_backtest, write_backtest_outputs
        from src.backtest.saa_backtest import run_saa_backtest, write_saa_backtest_outputs

        saa_bt = run_saa_backtest(data_dir, profile=profile)
        write_saa_backtest_outputs(saa_bt, output_dir)
        bt = run_regime_backtest(data_dir, profile=profile)
        write_backtest_outputs(bt, output_dir)

    alpha_bt_ran = False
    if run_alpha_backtest and (data_dir / "prices_history.csv").exists():
        from src.backtest.alpha_backtest import run_alpha_lite_backtest, write_alpha_backtest_outputs

        abt = run_alpha_lite_backtest(data_dir)
        write_alpha_backtest_outputs(abt, output_dir)
        alpha_bt_ran = True

    try:
        from src.hakedaka_gate import run_research_automation

        run_research_automation(data_dir, output_dir)
    except Exception:
        pass

    from src.exposure.look_through import (
        build_exposure_lookthrough,
        write_exposure_lookthrough,
    )

    exposure_report = build_exposure_lookthrough(
        positions, targets, data_dir, as_of=market.date,
    )
    write_exposure_lookthrough(exposure_report, output_dir / "exposure_lookthrough.json")

    from src.exposure.core_saa_reference import (
        build_core_saa_reference_diagnostic,
        write_core_saa_reference_diagnostic,
    )

    core_ref_diag = build_core_saa_reference_diagnostic(data_dir, as_of=market.date)
    if core_ref_diag:
        write_core_saa_reference_diagnostic(
            core_ref_diag, output_dir / "core_saa_reference_diagnostic.json",
        )

    if (data_dir / "absolute_return_policy.yaml").exists():
        write_absolute_return_status(data_dir, output_dir)

    from src.timing.asset_accumulation_timing import write_asset_accumulation_timing

    write_asset_accumulation_timing(
        data_dir=data_dir,
        output_dir=output_dir,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        throttle_meta=throttle_meta,
    )

    return PostDecisionArtifactsResult(
        cache_hit=False,
        reused=False,
        recomputed=["post_decision_artifacts"],
        exposure_report=exposure_report,
        alpha_backtest_ran=alpha_bt_ran,
    )


def maybe_run_post_decision_artifacts(
    core: FinalDecisionCoreResult,
    *,
    data_dir: Path,
    output_dir: Path,
    profile: str | None,
    run_backtest: bool,
    run_alpha_backtest: bool,
    rules: Any,
    positions: list[Any],
    run_mode: str = "standard",
    force_refresh: bool = False,
    profiler: Any | None = None,
    run_id: str = "",
) -> PostDecisionArtifactsResult:
    """Cache-first wrapper for post-decision artifacts."""
    t0 = time.perf_counter()
    decision = evaluate_post_decision_cache(
        data_dir,
        output_dir,
        run_mode=run_mode,
        force_refresh=force_refresh,
    )
    safety = validate_final_decision_safety(output_dir, data_dir)

    if decision["cache_hit"]:
        elapsed = time.perf_counter() - t0
        manifest = {
            "schema_version": "1.0",
            "generated_at": _utc_now(),
            "run_id": run_id,
            "run_mode": run_mode,
            "cache_hit": True,
            "skip_reason": decision["skip_reason"],
            "combined_input_hash": decision["combined_input_hash"],
            "input_hashes": decision["input_hashes"],
            "reused_artifacts": list(REQUIRED_ARTIFACT_OUTPUTS),
            "recomputed": [],
            "safety_check": safety,
        }
        write_post_decision_manifest(output_dir, manifest)
        result = PostDecisionArtifactsResult(
            cache_hit=True,
            reused=True,
            recomputed=[],
            skip_reason=str(decision["skip_reason"]),
            elapsed_seconds=elapsed,
            exposure_report=_load_exposure_report(output_dir),
            alpha_backtest_ran=False,
            combined_input_hash=decision["combined_input_hash"],
            safety=safety,
        )
        _apply_profiler(profiler, result)
        return result

    result = run_post_decision_artifacts(
        core,
        data_dir=data_dir,
        output_dir=output_dir,
        profile=profile,
        run_backtest=run_backtest,
        run_alpha_backtest=run_alpha_backtest,
        rules=rules,
        positions=positions,
    )
    result.elapsed_seconds = time.perf_counter() - t0
    result.combined_input_hash = decision["combined_input_hash"]
    result.safety = validate_final_decision_safety(output_dir, data_dir)
    manifest = {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "run_id": run_id,
        "run_mode": run_mode,
        "cache_hit": False,
        "skip_reason": "recomputed",
        "combined_input_hash": decision["combined_input_hash"],
        "input_hashes": decision["input_hashes"],
        "reused_artifacts": [],
        "recomputed": list(result.recomputed),
        "safety_check": result.safety,
    }
    write_post_decision_manifest(output_dir, manifest)
    _apply_profiler(profiler, result)
    return result


def _apply_profiler(profiler: Any | None, result: PostDecisionArtifactsResult) -> None:
    if profiler is None:
        return
    mapping = {
        "post_decision_artifacts_seconds": round(result.elapsed_seconds, 4),
        "post_decision_artifacts_cache_hit": result.cache_hit,
        "post_decision_artifacts_reused": result.reused,
        "post_decision_artifacts_recomputed": list(result.recomputed),
    }
    for key, val in mapping.items():
        if hasattr(profiler, key):
            setattr(profiler, key, val)
