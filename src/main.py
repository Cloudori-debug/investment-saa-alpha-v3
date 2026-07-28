from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from src.compass.profile_options import PROFILE_CLI_CHOICES
from src.runtime.cli import add_run_mode_argument, bootstrap_target_if_needed, execute_pipeline_with_run_mode
from src.runtime.run_mode import RunMode, resolve_run_config


def _safe_print(msg: str, *, file: Any = None) -> None:
    stream = file or sys.stdout
    try:
        print(msg, file=stream)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        text = msg.encode(enc, errors="replace").decode(enc, errors="replace")
        print(text, file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Multi-Asset Trigger Portfolio — 전체 파이프라인 (나침반+분해+실행+백테스트)"
    )
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument(
        "--profile",
        choices=PROFILE_CLI_CHOICES,
        default=None,
    )
    parser.add_argument("--no-decompose", action="store_true")
    parser.add_argument("--no-backtest", action="store_true")
    parser.add_argument(
        "--approve-target",
        action="store_true",
        help="Allow absolute_return_policy to overwrite data/target_portfolio.csv (explicit approval)",
    )
    parser.add_argument(
        "--refresh-market",
        action="store_true",
        help=(
            "Force Tier-1 market_indicators + Tier-A prices network refresh "
            "and regime auto-sync (overrides standard mode cache-first policy)"
        ),
    )
    add_run_mode_argument(parser)
    args = parser.parse_args(argv)

    try:
        bootstrap_target_if_needed(args.data_dir, approve_target=args.approve_target)

        cfg = resolve_run_config(args.run_mode)
        refresh_market = True if args.refresh_market else cfg.refresh_network
        pipe = execute_pipeline_with_run_mode(
            args.data_dir,
            args.output_dir,
            run_mode=args.run_mode,
            entrypoint="cli",
            auto_decompose=not args.no_decompose,
            run_backtest=not args.no_backtest if cfg.run_mode != RunMode.BUNDLE_ONLY else False,
            refresh_market=refresh_market,
            profile=args.profile,
        )

        _safe_print(f"Run mode: {pipe.run_mode} | entrypoint: cli")
        _safe_print(f"Actual Buy Allowed: {pipe.actual_buy_allowed}")
        if pipe.advisory_note:
            _safe_print(pipe.advisory_note)
        if pipe.data_gate:
            _safe_print(f"Data Gate: {pipe.data_gate}")
        _safe_print(f"Outputs: {args.output_dir.resolve()}")

        from src.validation.system_health import run_system_health, write_health_report

        report = run_system_health(args.data_dir, args.output_dir)
        write_health_report(report, args.output_dir / "system_health.json")
        _safe_print(
            f"Health: {report.overall} "
            f"(pass={report.summary.get('pass', 0)} warn={report.summary.get('warn', 0)} "
            f"fail={report.summary.get('fail', 0)})"
        )

        gate = pipe.data_gate or "GREEN"
        return 0 if gate != "RED" else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
