"""CLI helpers — shared --run-mode parsing and pipeline execution."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.runtime.pipeline_runner import PipelineRunResult, run_pipeline_with_mode
from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config

RUN_MODE_VALUES: tuple[str, ...] = tuple(m.value for m in RunMode)
INVALID_RUN_MODE_MSG = f"Invalid run_mode. Choose one of: {', '.join(RUN_MODE_VALUES)}"


def parse_run_mode(value: str | RunMode | None) -> RunMode:
    if isinstance(value, RunMode):
        return value
    raw = str(value or RunMode.STANDARD.value).strip().lower()
    try:
        return RunMode(raw)
    except ValueError as exc:
        raise SystemExit(INVALID_RUN_MODE_MSG) from exc


def run_mode_arg(value: str) -> str:
    raw = str(value).strip().lower()
    if raw not in RUN_MODE_VALUES:
        raise argparse.ArgumentTypeError(INVALID_RUN_MODE_MSG)
    return raw


def add_run_mode_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run-mode",
        type=run_mode_arg,
        default=RunMode.STANDARD.value,
        metavar="MODE",
        help=f"Pipeline run mode ({', '.join(RUN_MODE_VALUES)}; default: standard)",
    )


def execute_pipeline_with_run_mode(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str | RunMode = RunMode.STANDARD,
    entrypoint: str = "cli",
    auto_decompose: bool = True,
    run_backtest: bool | None = None,
    refresh_market: bool | None = None,
    profile: str | None = None,
) -> PipelineRunResult:
    """Shared CLI/Streamlit entry — identical run-mode policy via pipeline_runner."""
    from src.validation.dry_run_log import make_run_id

    mode = parse_run_mode(run_mode)
    cfg = resolve_run_config(mode)
    prof = RuntimeProfiler(
        run_id=make_run_id(),
        run_mode=cfg.run_mode.value,
        entrypoint=entrypoint,
    )
    if entrypoint == "cli":
        from src.runtime.cli_progress import cli_progress_callback, print_cli_run_header

        prof.on_step = cli_progress_callback
        print_cli_run_header(run_mode=cfg.run_mode.value, entrypoint=entrypoint)
    return run_pipeline_with_mode(
        data_dir,
        output_dir,
        run_mode=mode,
        auto_decompose=auto_decompose,
        refresh_market=refresh_market,
        run_backtest=run_backtest,
        profiler=prof,
        entrypoint=entrypoint,
        profile=profile,
    )


def bootstrap_target_if_needed(data_dir: Path, *, approve_target: bool = False) -> None:
    if not (data_dir / "absolute_return_policy.yaml").exists():
        return
    if approve_target:
        from src.exposure.absolute_return_policy import write_absolute_return_target_portfolio

        write_absolute_return_target_portfolio(data_dir, approve=True)
        return
    from src.alpha.target_portfolio_guard import bootstrap_user_target_if_missing

    bootstrap_user_target_if_missing(data_dir)
