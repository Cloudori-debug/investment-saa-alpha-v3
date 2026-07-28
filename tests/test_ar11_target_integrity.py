"""Phase AR-1.1 domestic_beta orphan and target integrity tests."""
from __future__ import annotations

from pathlib import Path

import yaml

from src.compass.compass_pipeline import run_compass_pipeline
from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.compass.target_decomposer import decompose_target_portfolio
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_positions, load_target_portfolio
from src.exposure.ar11_target_integrity import (
    get_locked_tilt_groups,
    redistribute_orphan_group_targets,
    zero_tilts_for_locked_groups,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def test_locked_tilt_groups_core_profile() -> None:
    profiles = load_saa_profiles(DATA / "saa_profiles.yaml")
    locked = get_locked_tilt_groups(profiles, "core_absolute_return")
    assert "domestic_beta" in locked
    assert zero_tilts_for_locked_groups({"domestic_beta": 1.0, "global_beta": 2.0}, locked)["domestic_beta"] == 0.0


def test_domestic_beta_zero_after_allocation() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_yaml(DATA / "compass_rules.yaml")
    profiles = load_saa_profiles(DATA / "saa_profiles.yaml")
    compass = compute_compass(market, rules, data_gate="GREEN", execution_level=1, tier2=None)
    allocation = build_portfolio_allocation(compass, profiles, profile_name="core_absolute_return")
    domestic = next(g for g in allocation.groups if g.asset_group == "domestic_beta")
    assert domestic.final_target == 0.0


def test_decomposed_targets_sum_100() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_yaml(DATA / "compass_rules.yaml")
    profiles = load_saa_profiles(DATA / "saa_profiles.yaml")
    template = load_target_portfolio(DATA / "target_portfolio.csv")
    compass = compute_compass(market, rules, data_gate="GREEN", execution_level=1, tier2=None)
    allocation = build_portfolio_allocation(compass, profiles, profile_name="core_absolute_return")
    rows = decompose_target_portfolio(allocation, template)
    assert abs(sum(r.target_weight for r in rows) - 100.0) < 0.01
    assert "069500" not in {r.ticker for r in rows}


def test_compass_pipeline_generated_sum_100(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    positions = load_positions(DATA / "positions.csv")
    template = load_target_portfolio(DATA / "target_portfolio.csv")
    result = run_compass_pipeline(
        DATA,
        out,
        profile="core_absolute_return",
        positions=positions,
        ticker_targets=template,
        template_targets=template,
        auto_decompose=True,
    )
    assert result.generated_targets
    total = sum(r.target_weight for r in result.generated_targets)
    assert abs(total - 100.0) < 0.01
    domestic = next(g for g in result.allocation.groups if g.asset_group == "domestic_beta")
    assert domestic.final_target == 0.0


def test_redistribute_orphan_groups() -> None:
    from src.compass.models import GroupAllocation, PortfolioAllocation, MarketPhase, RiskRegime

    allocation = PortfolioAllocation(
        profile="core_absolute_return",
        market_phase=MarketPhase.MARKET_EXPANSION,
        applied_regime=RiskRegime.YELLOW_STABLE,
        compass_direction="NE",
        groups=[
            GroupAllocation(
                asset_group="domestic_beta",
                saa_weight=0,
                phase_tilt=1,
                regime_tilt=0,
                raw_target=1,
                final_target=1.01,
                min_weight=0,
                max_weight=0,
            ),
            GroupAllocation(
                asset_group="global_beta",
                saa_weight=25.5,
                phase_tilt=0,
                regime_tilt=0,
                raw_target=25.5,
                final_target=25.94,
                min_weight=18,
                max_weight=35,
            ),
        ],
        total_weight=100,
        notes=[],
    )
    template = load_target_portfolio(DATA / "target_portfolio.csv")
    new_alloc, orphan, _ = redistribute_orphan_group_targets(allocation, template)
    assert orphan == 1.01
    domestic = next(g for g in new_alloc.groups if g.asset_group == "domestic_beta")
    assert domestic.final_target == 0.0
