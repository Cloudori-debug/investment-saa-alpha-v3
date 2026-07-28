"""Orchestrate Method B backtest end-to-end."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.backtest.compass_method_b.data import build_method_b_input
from src.backtest.compass_method_b.performance import compute_performance
from src.backtest.compass_method_b.replay import replay_compass
from src.backtest.compass_method_b.report import write_method_b_outputs
from src.backtest.compass_method_b.stats import count_regime_cycles, deflated_sharpe_ratio, is_oos_split
from src.compass.saa_engine import load_saa_profiles
from src.config import load_yaml


def run_method_b_backtest(
    data_dir: Path,
    output_dir: Path | None = None,
    *,
    n_trials: int = 16,
    warmup_trading_days: int = 200,
    profile_name: str = "core_absolute_return",
) -> dict[str, Any]:
    root = data_dir.parent if data_dir.name == "data" else data_dir
    # Prefer repo root / outputs/backtest
    out = output_dir or (root / "outputs" / "backtest")
    out.mkdir(parents=True, exist_ok=True)

    rules = load_yaml(data_dir / "compass_rules.yaml")
    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")

    panel, data_notes = build_method_b_input(data_dir)
    panel.to_csv(out / "compass_method_b_input.csv", index=False)

    results, judgment_history = replay_compass(
        panel,
        rules,
        profiles,
        warmup_trading_days=warmup_trading_days,
        profile_name=profile_name,
    )
    path, perf_summary = compute_performance(
        panel, results, profiles, profile_name=profile_name,
    )

    stats: dict[str, Any] = {
        "cycles": count_regime_cycles(results),
        "dsr_excess": deflated_sharpe_ratio(path["ret_excess"], n_trials=n_trials),
        "dsr_taa": deflated_sharpe_ratio(path["ret_taa"], n_trials=n_trials),
        "is_oos": is_oos_split(path, split_date="2021-01-01", n_trials=n_trials),
        "n_trials_rationale": (
            "n_trials=16 approximates ≥15 free parameters "
            "(indicators × thresholds) per Harvey–Liu–Zhu / Method B SPEC §4"
        ),
    }

    write_method_b_outputs(
        out,
        panel=panel,
        results=results,
        path=path,
        data_notes=data_notes,
        perf_summary=perf_summary,
        stats=stats,
        judgment_history=judgment_history,
    )

    return {
        "output_dir": str(out),
        "data_notes": data_notes,
        "perf_summary": perf_summary,
        "stats": stats,
    }
