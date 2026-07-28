from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.action_planner import plan_actions
from src.alpha.alpha_pipeline import (
    load_asset_targets_from_output,
    load_regime_from_output,
    run_alpha_pipeline,
)
from src.backtest.regime_backtest import run_regime_backtest, write_backtest_outputs
from src.compass.compass_pipeline import CompassPipelineResult, run_compass_pipeline
from src.config import load_portfolio_policy, load_trigger_rules
from src.data_loader import (
    load_market_indicators_bundle,
    load_positions,
    load_target_portfolio,
    write_market_indicators_normalized,
)
from src.decision_logger import append_decision_log
from src.portfolio_gap import compute_gaps
from src.final_execution_decision import (
    GROUP_GAP_SOURCE_COMPASS,
    GROUP_GAP_SOURCE_TICKER,
    build_final_execution_decision,
    write_final_execution_decision,
)
from src.regime_classifier import classify_data_gate_from_regime, execution_level_hint, parse_regime
from src.report_writer import (
    write_current_vs_target,
    write_trade_actions,
    write_trigger_alerts,
)
from src.risk_limits import check_risk_limits
from src.trigger_engine import evaluate_triggers
from src.operational_gate import gate_from_health_checks, resolve_operational_gate
from src.operational_gate import explain_operational_gate, health_warn_summaries
from src.data_provenance import audit_market_data_consistency
from src.trigger_engine import is_buy_trigger_active, is_stop_buy
from src.unified_data_gate import effective_data_gate
from src.validation.system_health import run_input_health_checks, run_system_health, write_health_report
from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report
from src.validation.dry_run_log import append_dry_run_log, make_run_id, write_run_manifest
from src.validators import validate_inputs
from src.models import TriggerStatus


@dataclass
class FullPipelineResult:
    compass: CompassPipelineResult | None
    data_gate: str
    execution_level: int
    action_count: int
    alpha_candidate_count: int = 0
    alpha_backtest_ran: bool = False


def run_full_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    profile: str | None = None,
    auto_decompose: bool = True,
    run_backtest: bool = True,
    run_alpha: bool = True,
    run_alpha_backtest: bool = True,
    run_mode_config: object | None = None,
    profiler: object | None = None,
    finalize_profiler: bool = True,
    pipeline_step_runner: object | None = None,
) -> FullPipelineResult:
    from contextlib import nullcontext

    def _step(name: str):
        if profiler is not None and hasattr(profiler, "step"):
            return profiler.step(name)
        return nullcontext()

    def _core_step(name: str, **kwargs: object):
        if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "step"):
            return pipeline_step_runner.step(name, **kwargs)
        return _step(name)

    def _begin_step(name: str, **kwargs: object) -> object | None:
        if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "step"):
            cm = pipeline_step_runner.step(name, **kwargs)
            cm.__enter__()
            return cm
        if profiler is not None and hasattr(profiler, "step"):
            cm = profiler.step(name)
            cm.__enter__()
            return cm
        return None

    def _end_step(cm: object | None) -> None:
        if cm is not None:
            cm.__exit__(None, None, None)

    cfg = run_mode_config
    if cfg is not None:
        run_alpha = bool(getattr(cfg, "run_alpha_v1", run_alpha))
        run_backtest = bool(getattr(cfg, "run_backtest", run_backtest))
        run_alpha_backtest = bool(getattr(cfg, "run_alpha_backtest", run_alpha_backtest))

    run_id = make_run_id()

    from src.exposure.absolute_return_policy import (
        write_absolute_return_status,
    )

    _portfolio_cm = _begin_step("portfolio_state_build")
    if (data_dir / "absolute_return_policy.yaml").exists():
        from src.alpha.target_portfolio_guard import (
            auto_restore_operational_target_if_needed,
            bootstrap_user_target_if_missing,
        )

        bootstrap_user_target_if_missing(data_dir)
        target_restore_meta = auto_restore_operational_target_if_needed(data_dir, output_dir)
    else:
        target_restore_meta = {"restored": False}

    from src.alpha.target_portfolio_guard import user_target_portfolio_path

    positions = load_positions(data_dir / "positions.csv")
    user_target_path = user_target_portfolio_path(data_dir)
    if user_target_path.exists():
        template_targets = load_target_portfolio(user_target_path)
    else:
        template_targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    market_path = data_dir / "market_indicators.csv"
    market_bundle = load_market_indicators_bundle(market_path)
    market = market_bundle.market
    policy = load_portfolio_policy(data_dir / "portfolio_policy.yaml")
    rules = load_trigger_rules(data_dir / "trigger_rules.yaml")
    _end_step(_portfolio_cm)

    compass_result: CompassPipelineResult | None = None
    _saa_cm = _begin_step("saa_taa_allocation")
    if (data_dir / "compass_rules.yaml").exists() and (data_dir / "saa_profiles.yaml").exists():
        compass_result = run_compass_pipeline(
            data_dir,
            output_dir,
            profile=profile,
            positions=positions,
            ticker_targets=template_targets,
            template_targets=template_targets,
            auto_decompose=auto_decompose,
            run_id=run_id,
        )
    _end_step(_saa_cm)

    generated_targets = (
        compass_result.generated_targets
        if compass_result and compass_result.generated_targets
        else None
    )
    if user_target_path.exists():
        targets = load_target_portfolio(user_target_path)
    elif generated_targets:
        targets = generated_targets
    else:
        targets = template_targets

    alpha_count = 0
    alpha_gate: str | None = None
    alpha_out = None
    if run_alpha and (data_dir / "universe.csv").exists():
        try:
            from src.hakedaka_gate import prepare_hakedaka_dart_pipeline

            prepare_hakedaka_dart_pipeline(data_dir, output_dir)
        except Exception:
            pass
        from src.data_refresh.prices_refresh import ensure_tier_a_prices

        as_of_for_prices = market.date if market.date else None
        if as_of_for_prices:
            from src.alpha_v2_gate import maybe_refresh_tier_prices_before_alpha

            maybe_refresh_tier_prices_before_alpha(
                data_dir,
                output_dir,
                as_of=as_of_for_prices,
                run_mode=getattr(cfg, "run_mode", None) if cfg is not None else "standard",
                profiler=profiler,
                run_id=run_id,
                step_runner=pipeline_step_runner,
            )
        regime = load_regime_from_output(output_dir) if compass_result else {}
        asset_targets = load_asset_targets_from_output(output_dir) if compass_result else {}
        _alpha_v1_cm = _begin_step("alpha_v1_pipeline")
        alpha_out = run_alpha_pipeline(
            data_dir,
            output_dir,
            positions=positions,
            targets=targets,
            regime=regime,
            asset_group_targets=asset_targets,
            run_mode_config=cfg,
        )
        alpha_count = len(alpha_out.result.candidates)
        alpha_gate = alpha_out.result.data_gate
        _end_step(_alpha_v1_cm)

        try:
            from src.alpha_shadow_policy import run_configured_alpha_shadows

            run_shadows = cfg is None or (
                bool(getattr(cfg, "run_alpha_v2", True))
                or bool(getattr(cfg, "run_flow_dashboard", True))
            )
            if run_shadows:
                from src.alpha_v2_gate import write_pipeline_input_snapshot

                write_pipeline_input_snapshot(
                    output_dir, data_dir, as_of=market.date, run_id=run_id,
                )
                run_configured_alpha_shadows(
                    data_dir,
                    output_dir,
                    run_id=run_id,
                    as_of=market.date,
                    positions=positions,
                    targets=targets,
                    append_log=append_decision_log,
                    run_mode_config=cfg,
                    profiler=profiler,
                    step_runner=pipeline_step_runner,
                )
        except Exception:
            pass

    from src.runtime.final_decision_core import FinalDecisionCoreInputs, run_final_decision_core
    from src.runtime.post_decision_artifacts import maybe_run_post_decision_artifacts

    _core_cm = _begin_step("final_decision_core")
    core_result = run_final_decision_core(
        FinalDecisionCoreInputs(
            data_dir=data_dir,
            output_dir=output_dir,
            run_id=run_id,
            positions=positions,
            targets=targets,
            market=market,
            market_bundle=market_bundle,
            policy=policy,
            rules=rules,
            compass_result=compass_result,
            alpha_out=alpha_out,
            alpha_gate=alpha_gate,
            alpha_count=alpha_count,
            generated_targets=generated_targets,
            profile=profile,
        ),
    )
    _end_step(_core_cm)
    if profiler is not None and hasattr(profiler, "final_decision_core_seconds"):
        profiler.final_decision_core_seconds = round(
            getattr(profiler, "step_timings", {}).get("final_decision_core", 0.0), 4,
        )

    data_gate = core_result.data_gate
    exec_level = core_result.exec_level
    execution_scope = core_result.final_decision.execution_scope
    actions = core_result.actions
    review_actions = core_result.review_actions
    theoretical_actions = core_result.theoretical_actions
    gap_rows = core_result.gap_rows
    alerts = core_result.alerts
    final_decision = core_result.final_decision
    final_doc = core_result.final_doc
    acceptance = core_result.acceptance
    health_report = core_result.health_report
    alpha_trade_permission = core_result.alpha_trade_permission
    alpha_position_action = core_result.alpha_position_action
    hard_stops_detail = core_result.hard_stops_detail
    policy_gate = core_result.policy_gate
    health_gate = core_result.health_gate

    run_mode_str = "standard"
    if profiler is not None and hasattr(profiler, "run_mode") and profiler.run_mode:
        run_mode_str = str(profiler.run_mode)
    elif cfg is not None and hasattr(cfg, "run_mode"):
        run_mode_str = str(getattr(cfg.run_mode, "value", cfg.run_mode))

    _do_backtest = run_backtest
    if _do_backtest is None and cfg is not None:
        _do_backtest = bool(getattr(cfg, "run_backtest", True))
    if _do_backtest is None:
        _do_backtest = True

    _artifact_cm = _begin_step("post_decision_artifacts")
    artifact_result = maybe_run_post_decision_artifacts(
        core_result,
        data_dir=data_dir,
        output_dir=output_dir,
        profile=profile,
        run_backtest=_do_backtest,
        run_alpha_backtest=run_alpha_backtest,
        rules=rules,
        positions=positions,
        run_mode=run_mode_str,
        profiler=profiler,
        run_id=run_id,
    )
    _end_step(_artifact_cm)
    if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "annotate_last_step"):
        if artifact_result.cache_hit:
            pipeline_step_runner.annotate_last_step(
                "post_decision_artifacts",
                cache_hit=True,
                cache_source=artifact_result.skip_reason or "inputs_unchanged",
            )

    exposure_report = artifact_result.exposure_report
    alpha_bt_ran = artifact_result.alpha_backtest_ran

    run_research = cfg is None or bool(getattr(cfg, "run_research_outputs", True))
    if run_research:
        from src.runtime.research_outputs_cache import maybe_run_research_outputs

        with _core_step("research_outputs"):
            research_result = maybe_run_research_outputs(
                data_dir,
                output_dir,
                as_of=market.date,
                run_id=run_id,
                run_mode=run_mode_str,
                profiler=profiler,
            )
        if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "annotate_last_step"):
            if research_result.cache_hit:
                pipeline_step_runner.annotate_last_step(
                    "research_outputs",
                    cache_hit=True,
                    cache_source=research_result.skip_reason or "dependency_unchanged",
                )
    else:
        opp_decision = None
        if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "record_skip"):
            pipeline_step_runner.record_skip("research_outputs", "run_mode_disabled")

    run_full_diag = cfg is None or bool(getattr(cfg, "run_full_diagnostics", True))
    if run_full_diag:
        with _step("diagnostics"):
            from src.runtime.diagnostics_cache import run_diagnostics_with_cache

            run_mode_str = "standard"
            if profiler is not None and hasattr(profiler, "run_mode") and profiler.run_mode:
                run_mode_str = str(profiler.run_mode)
            elif cfg is not None and hasattr(cfg, "run_mode"):
                run_mode_str = str(getattr(cfg.run_mode, "value", cfg.run_mode))
            cache_result = run_diagnostics_with_cache(
                data_dir,
                output_dir,
                run_id=run_id,
                clarity=None,
                run_full_diag=True,
                run_mode=run_mode_str,
                profiler=profiler,
            )
            if profiler is not None and hasattr(profiler, "add_note"):
                if cache_result.cache_hit_count:
                    profiler.add_note(
                        f"Diagnostics cache: {cache_result.cache_hit_count} hits, "
                        f"~{cache_result.saved_seconds_estimate:.0f}s saved",
                    )
                if cache_result.recomputed:
                    profiler.add_note(f"Diagnostics recomputed: {', '.join(cache_result.recomputed[:6])}")

    run_reconcile = cfg is None or bool(getattr(cfg, "run_bundle_reconcile", True))
    if run_reconcile:
        from src.runtime.bundle_reconcile_cache import reconcile_bundle_artifacts_with_cache

        with _step("bundle_reconcile"):
            reconcile_bundle_artifacts_with_cache(
                data_dir,
                output_dir,
                run_id=run_id,
                as_of=market.date,
                target_restore_meta=target_restore_meta,
                profiler=profiler,
            )

    shadow_history_summary: dict | None = None
    run_shadow_hist = cfg is None or bool(getattr(cfg, "run_shadow_history", True))
    if run_shadow_hist:
        from src.runtime.shadow_history_cache import maybe_append_shadow_history

        with _core_step("shadow_history"):
            shadow_hist_result = maybe_append_shadow_history(
                data_dir,
                output_dir,
                run_id=run_id,
                run_date=market.date,
                run_mode=run_mode_str,
                profiler=profiler,
            )
        if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "annotate_last_step"):
            if shadow_hist_result.cache_hit:
                pipeline_step_runner.annotate_last_step(
                    "shadow_history",
                    cache_hit=True,
                    cache_source=shadow_hist_result.skip_reason or "semantic_snapshot_unchanged",
                )
        shadow_history_summary = shadow_hist_result.ledger_summary
    elif pipeline_step_runner is not None and hasattr(pipeline_step_runner, "record_skip"):
        pipeline_step_runner.record_skip("shadow_history", "run_mode_disabled")

    from src.runtime.report_export_cache import ReportExportWriteContext, maybe_run_report_exports

    with _core_step("report_exports"):
        export_result = maybe_run_report_exports(
            ReportExportWriteContext(
                data_dir=data_dir,
                output_dir=output_dir,
                run_id=run_id,
                as_of=market.date,
                acceptance=acceptance,
                data_gate=data_gate,
                market=market,
                gap_rows=gap_rows,
                alerts=alerts,
                actions=actions,
                execution_level=exec_level,
                policy_gate=policy_gate,
                health_gate=health_gate,
                theoretical_actions=theoretical_actions,
                review_actions=review_actions,
                health_overall=health_report.overall,
                execution_scope=execution_scope,
                alpha_trade_permission=alpha_trade_permission,
                alpha_position_action=alpha_position_action,
                hard_stops_detail=hard_stops_detail,
                exposure_lookthrough=exposure_report,
                shadow_history_summary=shadow_history_summary,
            ),
            run_mode=run_mode_str,
            profiler=profiler,
        )
    if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "annotate_last_step"):
        if export_result.cache_hit:
            pipeline_step_runner.annotate_last_step(
                "report_exports",
                cache_hit=True,
                cache_source=export_result.skip_reason or "dependency_unchanged",
            )
    daily_brief = export_result.daily_brief

    from src.report.execution_metrics import validate_report_clarity

    clarity = validate_report_clarity(output_dir)
    (output_dir / "report_clarity_validation.json").write_text(
        __import__("json").dumps(clarity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    from src.validation.fail_soft_pipeline import write_fail_soft_artifacts

    cross_val_path = output_dir / "output_cross_validation.json"
    cross_val = None
    if cross_val_path.exists():
        cross_val = __import__("json").loads(cross_val_path.read_text(encoding="utf-8"))
    write_fail_soft_artifacts(
        output_dir=output_dir,
        data_dir=data_dir,
        run_id=run_id,
        as_of=market.date,
        final_decision=final_decision.to_dict(),
        clarity=clarity,
        cross_val=cross_val,
    )

    from src.validation.ai_export import sync_export_clarity_artifacts

    sync_export_clarity_artifacts(output_dir)

    if market.date:
        from src.alpha_v2_gate import commit_pipeline_input_snapshot

        with _core_step("post_run_commit_snapshot"):
            commit_pipeline_input_snapshot(
                output_dir, data_dir, as_of=market.date, run_id=run_id,
            )

    if pipeline_step_runner is not None and hasattr(pipeline_step_runner, "write"):
        pipeline_step_runner.write(output_dir)

    if profiler is not None and finalize_profiler and hasattr(profiler, "write"):
        with _step("runtime_profile"):
            profiler.write(output_dir)

    return FullPipelineResult(
        compass=compass_result,
        data_gate=data_gate,
        execution_level=exec_level,
        action_count=len(actions),
        alpha_candidate_count=alpha_count,
        alpha_backtest_ran=alpha_bt_ran,
    )


def _build_gate_notes(input_health, alpha_data_gate: str | None, execution_scope: str) -> list[str]:
    notes: list[str] = []
    for check in input_health.checks:
        if check.name == "prices_coverage":
            notes.append(check.message)
            break
    if alpha_data_gate:
        notes.append(f"Alpha 재무 PIT gate: {alpha_data_gate}")
    notes.append(f"Execution scope: {execution_scope}")
    return notes


def _patch_compass_regime_gate(
    output_dir: Path,
    data_gate: str,
    execution_level: int,
    execution_scope: str | None = None,
) -> None:
    path = output_dir / "compass_regime.json"
    if not path.exists():
        return
    import json as _json

    data = _json.loads(path.read_text(encoding="utf-8"))
    data["data_gate"] = data_gate
    data["execution_level"] = execution_level
    if execution_scope:
        data["execution_scope"] = execution_scope
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _patch_gpt_context_gate(
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
    import json as _json

    ctx = _json.loads(path.read_text(encoding="utf-8"))
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
    path.write_text(_json.dumps(ctx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from src.main import main

    raise SystemExit(main())
