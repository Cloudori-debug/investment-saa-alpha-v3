"""Pipeline runners — quick / standard / deep / bundle_only."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config


@dataclass
class PipelineRunResult:
    run_mode: str
    run_id: str
    actual_buy_allowed: int = 0
    data_gate: str | None = None
    execution_scope: str | None = None
    advisory_note: str = ""
    warnings: list[str] = field(default_factory=list)
    bundle_created: bool = False
    zip_bytes: int = 0


def _actual_buy_from_outputs(output_dir: Path) -> int:
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    if not final_doc:
        return 0
    return int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)


def _validate_target_guard(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    from src.validation.system_health import run_input_health_checks

    as_of = ""
    mi_path = data_dir / "market_indicators.csv"
    if mi_path.exists():
        import pandas as pd

        df = pd.read_csv(mi_path, dtype=str, nrows=1)
        if not df.empty and "date" in df.columns:
            as_of = str(df.iloc[0]["date"])
    health = run_input_health_checks(data_dir, as_of=as_of or None, output_dir=output_dir)
    guard = next((c for c in health.checks if c.name == "target_portfolio_guard"), None)
    return {
        "overall": health.overall,
        "target_guard_status": guard.status if guard else "unknown",
        "target_guard_message": guard.message if guard else "",
    }


def _refresh_daily_report_authoritative_top(output_dir: Path) -> None:
    """Quick mode — refresh authoritative block without full report recompute."""
    from src.report_writer import build_daily_report_status_summary

    path = output_dir / "daily_report.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    section1_idx = text.find("\n## 1.")
    tail = text[section1_idx:] if section1_idx >= 0 else ""
    runtime_marker = "### Runtime / Run Mode"
    runtime_block = ""
    if runtime_marker in text:
        runtime_block = text[text.index(runtime_marker):]
        if section1_idx >= 0 and text.index(runtime_marker) < section1_idx:
            runtime_block = ""
    summary_lines = build_daily_report_status_summary(output_dir)
    sh_path = output_dir / "system_health.json"
    health_line = ""
    if sh_path.exists():
        import json

        sh = json.loads(sh_path.read_text(encoding="utf-8"))
        health_line = f"- **system_health_overall**: {str(sh.get('overall', '—')).upper()}"
    top_parts = [health_line] if health_line else []
    top_parts.extend(summary_lines)
    new_top = "\n".join(p for p in top_parts if p)
    if tail:
        new_body = new_top + "\n\n" + tail.lstrip("\n")
    else:
        new_body = new_top
    if runtime_block and runtime_block not in new_body:
        new_body = new_body.rstrip() + "\n\n" + runtime_block.strip() + "\n"
    path.write_text(new_body, encoding="utf-8")
    from src.report.execution_metrics import sync_daily_report_system_health_overall

    sync_daily_report_system_health_overall(output_dir)


def _write_light_daily_report_append(output_dir: Path, *, run_mode: str, note: str, actual_buy: int) -> None:
    path = output_dir / "daily_report.md"
    block = "\n".join(
        [
            "",
            "### Runtime / Run Mode",
            f"- **Run mode**: `{run_mode}`",
            f"- **Advisory**: {note}",
            f"- **Actual Buy Allowed**: {actual_buy}",
            "",
        ]
    )
    if path.exists():
        text = path.read_text(encoding="utf-8")
        marker = "### Runtime / Run Mode"
        if marker in text:
            head = text.split(marker, 1)[0].rstrip()
            path.write_text(head + block, encoding="utf-8")
        else:
            path.write_text(text.rstrip() + block, encoding="utf-8")
    else:
        path.write_text(f"# Daily Report\n{block}", encoding="utf-8")


def run_quick_check(
    data_dir: Path,
    output_dir: Path,
    *,
    profiler: RuntimeProfiler | None = None,
    entrypoint: str = "unknown",
    on_step: Callable[[str, str, float], None] | None = None,
) -> PipelineRunResult:
    from src.validation.dry_run_log import make_run_id
    from src.validation.no_action_diagnostics import write_no_action_diagnostics
    from src.report.execution_metrics import validate_report_clarity

    run_id = make_run_id()
    prof = profiler or RuntimeProfiler(
        run_id=run_id, run_mode=RunMode.QUICK.value, entrypoint=entrypoint,
    )
    if on_step:
        prof.on_step = on_step
    cfg = resolve_run_config(RunMode.QUICK)

    with prof.step("target_guard"):
        guard = _validate_target_guard(data_dir, output_dir)
        if guard.get("target_guard_status") == "fail":
            prof.add_note(f"target_guard={guard.get('target_guard_status')}")

    with prof.step("authoritative_status"):
        from src.report.authoritative_status import resolve_authoritative_execution
        from src.report.io_utils import read_output_json

        final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
        auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc)
        data_gate = str(auth.get("unified_data_gate") or final_doc.get("data_gate") or "—")
        scope = str(auth.get("execution_scope") or final_doc.get("execution_scope") or "—")

    with prof.step("actual_buy_allowed"):
        actual_buy = _actual_buy_from_outputs(output_dir)
        prof.add_note(f"Actual Buy Allowed validated from existing final_execution_decision: {actual_buy}")

    with prof.step("diagnostics"):
        data_dir = output_dir.parent / "data"
        if data_dir.exists():
            from src.report.authoritative_status import (
                patch_alpha_v2_execution_context,
                sync_acceptance_authoritative_scope_fields,
            )

            sync_acceptance_authoritative_scope_fields(data_dir, output_dir)
            patch_alpha_v2_execution_context(data_dir, output_dir)
        clarity = validate_report_clarity(output_dir)
        (output_dir / "report_clarity_validation.json").write_text(
            json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_no_action_diagnostics(data_dir, output_dir, clarity=clarity, light=True)

    with prof.step("daily_report"):
        _refresh_daily_report_authoritative_top(output_dir)
        _write_light_daily_report_append(
            output_dir,
            run_mode=cfg.run_mode.value,
            note=cfg.advisory_note,
            actual_buy=actual_buy,
        )

    with prof.step("runtime_profile"):
        prof.write(output_dir)

    total_seconds = round(sum(prof.step_timings.values()), 4)
    from src.runtime.quick_mode_validation import write_quick_mode_validation

    write_quick_mode_validation(
        output_dir,
        data_dir,
        run_id=run_id,
        profiler=prof,
        total_seconds=total_seconds,
        actual_buy_allowed=actual_buy,
        target_guard_status=str(guard.get("target_guard_status") or "unknown"),
    )

    return PipelineRunResult(
        run_mode=RunMode.QUICK.value,
        run_id=run_id,
        actual_buy_allowed=actual_buy,
        data_gate=data_gate,
        execution_scope=scope,
        advisory_note=cfg.advisory_note,
    )


def run_bundle_only(
    data_dir: Path,
    output_dir: Path,
    *,
    profiler: RuntimeProfiler | None = None,
    create_zip: bool = True,
    entrypoint: str = "unknown",
    on_step: Callable[[str, str, float], None] | None = None,
) -> PipelineRunResult:
    from src.validation.dry_run_log import make_run_id
    from src.validation.ai_export import build_export_zip, prepare_export_bundle_existing_only

    run_id = make_run_id()
    prof = profiler or RuntimeProfiler(
        run_id=run_id, run_mode=RunMode.BUNDLE_ONLY.value, entrypoint=entrypoint,
    )
    if on_step:
        prof.on_step = on_step
    cfg = resolve_run_config(RunMode.BUNDLE_ONLY)
    warnings: list[str] = []

    if not (output_dir / "run_manifest.json").exists():
        raise FileNotFoundError("run_manifest.json 없음 — 전체 분석을 먼저 실행하세요.")

    with prof.step("target_guard"):
        guard = _validate_target_guard(data_dir, output_dir)
        if guard.get("target_guard_status") == "fail":
            warnings.append("target_guard FAIL — bundle created for review only")

    with prof.step("authoritative_status"):
        actual_buy = _actual_buy_from_outputs(output_dir)

    with prof.step("report_clarity_validation"):
        from src.report.execution_metrics import validate_report_clarity

        clarity = validate_report_clarity(output_dir)
        (output_dir / "report_clarity_validation.json").write_text(
            json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    zip_len = 0
    with prof.step("ai_export_bundle"):
        bundle = prepare_export_bundle_existing_only(data_dir, output_dir)
        prof.generated_files_count += 1

    if create_zip and cfg.run_zip_bundle:
        with prof.step("zip_bundle"):
            zip_bytes = build_export_zip(bundle)
            zip_len = len(zip_bytes)
            prof.bundle_size_mb = round(zip_len / (1024 * 1024), 3)

    with prof.step("runtime_profile"):
        prof.write(output_dir)

    return PipelineRunResult(
        run_mode=RunMode.BUNDLE_ONLY.value,
        run_id=run_id,
        actual_buy_allowed=actual_buy,
        advisory_note=cfg.advisory_note,
        warnings=warnings,
        bundle_created=True,
        zip_bytes=zip_len,
    )


def run_pipeline_with_mode(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str | RunMode = RunMode.STANDARD,
    auto_decompose: bool = True,
    refresh_market: bool | None = None,
    run_backtest: bool | None = None,
    profiler: RuntimeProfiler | None = None,
    entrypoint: str = "unknown",
    profile: str | None = None,
    on_step: Callable[[str, str, float], None] | None = None,
) -> PipelineRunResult:
    cfg = resolve_run_config(run_mode)
    if cfg.is_bundle_only:
        return run_bundle_only(data_dir, output_dir, profiler=profiler, entrypoint=entrypoint, on_step=on_step)

    if cfg.run_mode == RunMode.QUICK:
        return run_quick_check(data_dir, output_dir, profiler=profiler, entrypoint=entrypoint, on_step=on_step)

    from src.validation.dry_run_log import make_run_id
    from src.full_pipeline import run_full_pipeline
    from src.runtime.pipeline_step_runner import PipelineStepRunner

    run_id = make_run_id()
    prof = profiler or RuntimeProfiler(
        run_id=run_id, run_mode=cfg.run_mode.value, entrypoint=entrypoint,
    )
    if on_step and prof.on_step is None:
        prof.on_step = on_step

    step_runner = PipelineStepRunner(
        run_mode=cfg.run_mode.value,
        run_id=run_id,
        profiler=prof,
        output_dir=output_dir,
    )

    do_refresh = cfg.refresh_network if refresh_market is None else refresh_market
    if do_refresh:
        with prof.step("data_refresh"):
            with step_runner.step("market_data_refresh"):
                from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

                try:
                    mi = refresh_all_market_indicators(data_dir)
                    prof.record_cache_miss()
                    mi_as_of = getattr(mi, "as_of", "") or ""
                except Exception as exc:
                    mi_as_of = ""
                    prof.add_note(f"market refresh failed: {exc}")
            with step_runner.step("tier_a_prices_refresh"):
                # Tier-1 as_of만 올리면 core_price_gate가 stale→RED로 악화됨.
                from src.data_refresh.prices_refresh import refresh_prices_snapshot

                try:
                    px_as_of = mi_as_of
                    if not px_as_of and (data_dir / "market_indicators.csv").exists():
                        import pandas as pd

                        midf = pd.read_csv(
                            data_dir / "market_indicators.csv", dtype=str, nrows=1
                        )
                        if not midf.empty and "date" in midf.columns:
                            px_as_of = str(midf.iloc[0]["date"])
                    px = refresh_prices_snapshot(data_dir, as_of=px_as_of or None)
                    prof.record_cache_miss()
                    if px.warnings:
                        prof.add_note(
                            "tier_a prices refresh warnings: "
                            + "; ".join(str(w) for w in px.warnings[:5])
                        )
                except Exception as exc:
                    prof.add_note(f"tier_a prices refresh failed: {exc}")
            with step_runner.step("regime_auto_sync"):
                from src.compass.regime_auto import sync_regime_from_compass

                try:
                    sync_regime_from_compass(
                        data_dir, output_dir, as_of=mi_as_of or None
                    )
                except Exception as exc:
                    prof.add_note(f"regime auto-sync failed: {exc}")
    elif cfg.run_mode in {RunMode.STANDARD, RunMode.DEEP}:
        step_runner.record_skip("market_data_refresh", "refresh_network_disabled")
        step_runner.record_skip("tier_a_prices_refresh", "refresh_network_disabled")
        step_runner.record_skip("regime_auto_sync", "refresh_network_disabled")

    with prof.step("target_guard"):
        with step_runner.step("target_guard_precheck"):
            _validate_target_guard(data_dir, output_dir)

    as_of = ""
    mi_path = data_dir / "market_indicators.csv"
    if mi_path.exists():
        import pandas as pd

        df = pd.read_csv(mi_path, dtype=str, nrows=1)
        if not df.empty and "date" in df.columns:
            as_of = str(df.iloc[0]["date"])

    if as_of and cfg.run_mode in {RunMode.STANDARD, RunMode.DEEP}:
        from src.runtime.run_hooks import run_deep_data_hooks

        with prof.step("data_hooks"):
            hooks_meta = run_deep_data_hooks(data_dir, output_dir, cfg, as_of=as_of, profiler=prof)
    else:
        hooks_meta = {}

    if as_of:
        from src.alpha_v2_gate import write_pipeline_input_snapshot

        write_pipeline_input_snapshot(output_dir, data_dir, as_of=as_of, run_id=run_id)

    with prof.step("pipeline_core"):
        result = run_full_pipeline(
            data_dir,
            output_dir,
            profile=profile,
            auto_decompose=auto_decompose,
            run_backtest=run_backtest if run_backtest is not None else cfg.run_backtest,
            run_alpha=cfg.run_alpha_v1,
            run_alpha_backtest=cfg.run_alpha_backtest,
            run_mode_config=cfg,
            profiler=prof,
            finalize_profiler=False,
            pipeline_step_runner=step_runner,
        )

    actual_buy = _actual_buy_from_outputs(output_dir)

    if cfg.run_zip_bundle:
        try:
            with prof.step("zip_bundle"):
                zip_res = run_bundle_only(
                    data_dir, output_dir, profiler=prof, create_zip=True, entrypoint=entrypoint,
                )
                actual_buy = zip_res.actual_buy_allowed or actual_buy
        except Exception as exc:
            prof.add_note(f"zip bundle skipped: {exc}")

    with prof.step("runtime_profile"):
        from src.runtime.run_mode_contract import validate_run_mode_contract, write_run_mode_contract_validation

        contract = validate_run_mode_contract(cfg, prof, hooks_meta=hooks_meta)
        write_run_mode_contract_validation(output_dir, contract)
        if not contract.get("contract_pass") and contract.get("violations"):
            prof.add_note(f"Run mode contract violations: {', '.join(contract['violations'][:3])}")
        prof.write(output_dir)

    return PipelineRunResult(
        run_mode=cfg.run_mode.value,
        run_id=run_id,
        actual_buy_allowed=actual_buy,
        data_gate=result.data_gate if result else None,
        advisory_note=cfg.advisory_note,
    )
