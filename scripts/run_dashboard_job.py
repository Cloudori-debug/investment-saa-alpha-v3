#!/usr/bin/env python3
"""Run a dashboard long job (quant snapshot or compass analysis) out of process.

Writes status to data/local/alpha_job.json. Does not write target_portfolio.csv.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard background job")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--kind", required=True, choices=("quant", "compass"))
    parser.add_argument("--collect-scope", default="liquid")
    parser.add_argument("--run-mode", default="standard")
    parser.add_argument("--market", default="KOSPI")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    from alpha_system.journal.recorder import configure_journal_path
    from alpha_system.ui.services.background_job import (
        apply_worker_result,
        load_job,
        update_phase,
    )
    from alpha_system.ui.services.runtime_state import RuntimeState

    configure_journal_path(root / "data" / "alpha_system_journal.jsonl")
    job = load_job(root)
    if job is not None and job.cancel_requested:
        apply_worker_result(
            root,
            ok=False,
            message="중단됨",
            phase="중단",
        )
        return 0

    try:
        if args.kind == "quant":
            from alpha_system.ui.services.refresh import run_quant_snapshot_refresh

            update_phase(root, "운용 데이터·alpha_scores 수집")
            result = run_quant_snapshot_refresh(
                root,
                collect_scope=str(args.collect_scope or "liquid"),
                market=str(args.market or "KOSPI"),
            )
            refresh_key = "alpha_quant_snapshot"
        else:
            from alpha_system.ui.services.refresh import run_compass_analysis

            update_phase(root, "나침반·레짐 분석 (Tier-1·레짐)")
            result = run_compass_analysis(root, run_mode=str(args.run_mode or "standard"))
            refresh_key = "compass_analysis"
    except Exception as exc:
        apply_worker_result(
            root,
            ok=False,
            message=str(exc),
            phase="실패",
            detail={"error": str(exc)},
        )
        return 1

    job = load_job(root)
    if job is not None and job.cancel_requested:
        apply_worker_result(
            root,
            ok=False,
            message="중단됨",
            phase="중단",
            detail=result.detail,
        )
        return 0

    apply_worker_result(
        root,
        ok=result.ok,
        message=result.message,
        phase="완료" if result.ok else "실패",
        detail=result.detail,
    )
    if result.ok:
        runtime_path = root / "data" / "alpha_dashboard_runtime.json"
        runtime = RuntimeState.load(runtime_path)
        runtime.touch_refresh(refresh_key)
        runtime.save(runtime_path)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
