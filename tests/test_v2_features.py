from __future__ import annotations

from pathlib import Path

import pytest

from src.compass.target_decomposer import decompose_target_portfolio
from src.compass.tier2_macro import load_macro_tier2, score_tier2_axes
from src.backtest.regime_backtest import run_regime_backtest
from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_target_portfolio
from src.full_pipeline import run_full_pipeline


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_tier2_load_and_score():
    macro = load_macro_tier2(DATA_DIR / "macro_tier2.csv")
    assert macro is not None
    rules = load_yaml(DATA_DIR / "compass_rules.yaml")
    axes, bd = score_tier2_axes(macro, rules)
    assert "growth" in axes
    assert len(bd) > 0


def test_tier2_blends_into_compass():
    market = load_market_indicators(DATA_DIR / "market_indicators.csv")
    rules = load_yaml(DATA_DIR / "compass_rules.yaml")
    tier2 = load_macro_tier2(DATA_DIR / "macro_tier2.csv")
    without = compute_compass(market, rules, tier2=None)
    with_t2 = compute_compass(market, rules, tier2=tier2)
    assert len(with_t2.score_breakdown) >= len(without.score_breakdown)


def test_decompose_targets_sum_to_100():
    market = load_market_indicators(DATA_DIR / "market_indicators.csv")
    rules = load_yaml(DATA_DIR / "compass_rules.yaml")
    profiles = load_saa_profiles(DATA_DIR / "saa_profiles.yaml")
    template = load_target_portfolio(DATA_DIR / "target_portfolio.csv")
    compass = compute_compass(market, rules)
    allocation = build_portfolio_allocation(compass, profiles)
    generated = decompose_target_portfolio(allocation, template)
    assert abs(sum(r.target_weight for r in generated) - 100) < 0.2
    group_sums: dict[str, float] = {}
    for r in generated:
        group_sums[r.asset_group] = group_sums.get(r.asset_group, 0) + r.target_weight
    for g in allocation.groups:
        if g.final_target > 0:
            assert abs(group_sums.get(g.asset_group, 0) - g.final_target) < 0.2


def test_backtest_runs():
    result = run_regime_backtest(DATA_DIR)
    assert len(result.rows) >= 5
    assert result.rows[0].date


def test_full_pipeline(tmp_path):
    out = tmp_path / "out"
    result = run_full_pipeline(DATA_DIR, out, run_backtest=True)
    assert result.compass is not None
    assert (out / "generated_target_portfolio.csv").exists()
    assert (out / "backtest_results.csv").exists()
    assert (out / "compass_regime.json").exists()
