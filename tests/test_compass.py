from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.compass.compass_pipeline import run_compass_pipeline
from src.compass.regime_json import build_regime_json_payload
from src.compass.group_action_planner import plan_group_actions
from src.compass.mismatch_check import check_target_mismatch
from src.compass.models import MarketPhase, RiskRegime, SCHEMA_VERSION
from src.compass.portfolio_builder import apply_bounds_iterative, build_portfolio_allocation
from src.compass.profile_aliases import resolve_profile_name
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import get_saa_weights, load_saa_profiles
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_positions, load_target_portfolio


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIXED_TS = "2026-06-17T00:00:00+00:00"


@pytest.fixture
def market():
    return load_market_indicators(DATA_DIR / "market_indicators.csv")


@pytest.fixture
def compass_rules():
    return load_yaml(DATA_DIR / "compass_rules.yaml")


@pytest.fixture
def saa_profiles():
    return load_saa_profiles(DATA_DIR / "saa_profiles.yaml")


def test_compute_compass_returns_valid_scores(market, compass_rules):
    result = compute_compass(market, compass_rules)
    assert result.market_phase in MarketPhase
    assert result.computed_regime in RiskRegime
    assert -1 <= result.growth_score <= 1
    assert len(result.signals) == 4
    assert len(result.score_breakdown) > 0
    assert result.compass_direction in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}


def test_manual_regime_override_logging(market, compass_rules):
    market.regime = "RISK_OFF"
    result = compute_compass(market, compass_rules)
    assert result.applied_regime == RiskRegime.RISK_OFF
    assert result.override.active is True
    assert result.override.timestamp == market.date


def test_profile_alias_balanced_to_core_absolute_return(saa_profiles):
    """Current SAA policy: balanced/conservative aliases → core_absolute_return."""
    assert resolve_profile_name(saa_profiles, "balanced") == "core_absolute_return"
    assert resolve_profile_name(saa_profiles, "conservative") == "core_absolute_return"
    assert resolve_profile_name(saa_profiles, "qvm_sr") == "core_absolute_return"
    assert resolve_profile_name(saa_profiles, None) == "core_absolute_return"
    assert resolve_profile_name(saa_profiles, "defensive_balanced") == "defensive_balanced"


def test_saa_weights_sum_to_100(saa_profiles):
    for name in ("core_absolute_return", "defensive_balanced"):
        weights = get_saa_weights(saa_profiles, name)
        assert abs(sum(weights.values()) - 100) < 0.01


def test_build_allocation_sums_to_100(market, compass_rules, saa_profiles):
    compass = compute_compass(market, compass_rules)
    allocation = build_portfolio_allocation(compass, saa_profiles, profile_name="balanced")
    assert abs(allocation.total_weight - 100) < 0.1
    assert allocation.profile == "core_absolute_return"
    for g in allocation.groups:
        assert g.min_weight - 0.01 <= g.final_target <= g.max_weight + 0.01


def test_crisis_increases_cash_vs_stable(market, compass_rules, saa_profiles):
    compass_stable = compute_compass(market, compass_rules)
    market.regime = "CRISIS"
    compass_crisis = compute_compass(market, compass_rules)

    alloc_stable = build_portfolio_allocation(compass_stable, saa_profiles)
    alloc_crisis = build_portfolio_allocation(compass_crisis, saa_profiles)

    cash_stable = next(g for g in alloc_stable.groups if g.asset_group == "cash_short_bond")
    cash_crisis = next(g for g in alloc_crisis.groups if g.asset_group == "cash_short_bond")
    assert cash_crisis.final_target > cash_stable.final_target


def test_clamp_iterative_respects_bounds_after_extreme_tilt():
    bounds = {
        "cash_short_bond": {"min": 25, "max": 55},
        "kr_alpha": {"min": 20, "max": 35},
        "domestic_beta": {"min": 5, "max": 15},
        "global_beta": {"min": 5, "max": 15},
        "fx_dollar": {"min": 0, "max": 6},
        "hedge_alt": {"min": 2, "max": 8},
        "income_alt": {"min": 0, "max": 5},
    }
    raw = {
        "cash_short_bond": 10,
        "kr_alpha": 50,
        "domestic_beta": 20,
        "global_beta": 20,
        "fx_dollar": 0,
        "hedge_alt": 0,
        "income_alt": 0,
    }
    final, _ = apply_bounds_iterative(raw, bounds)
    assert abs(sum(final.values()) - 100) < 0.1
    for group, w in final.items():
        b = bounds[group]
        assert b["min"] - 0.05 <= w <= b["max"] + 0.05


def test_crisis_cash_above_policy_minimum(market, compass_rules, saa_profiles):
    market.regime = "CRISIS"
    compass = compute_compass(market, compass_rules)
    allocation = build_portfolio_allocation(compass, saa_profiles)
    cash = next(g for g in allocation.groups if g.asset_group == "cash_short_bond")
    assert cash.final_target >= cash.min_weight - 0.05
    assert cash.final_target <= cash.max_weight + 0.05


def test_risk_on_kr_alpha_within_max(market, compass_rules, saa_profiles):
    market.regime = "RISK_ON"
    compass = compute_compass(market, compass_rules)
    allocation = build_portfolio_allocation(compass, saa_profiles)
    alpha = next(g for g in allocation.groups if g.asset_group == "kr_alpha")
    assert alpha.final_target <= alpha.max_weight + 0.05


def test_deterministic_json_hash(market, compass_rules, saa_profiles, tmp_path):
    compass1 = compute_compass(market, compass_rules)
    alloc1 = build_portfolio_allocation(compass1, saa_profiles)
    payload1 = build_regime_json_payload(compass1, alloc1, generated_at=FIXED_TS)
    del payload1["generated_at"]
    hash1 = hashlib.sha256(json.dumps(payload1, sort_keys=True).encode()).hexdigest()

    market2 = deepcopy(market)
    compass2 = compute_compass(market2, compass_rules)
    alloc2 = build_portfolio_allocation(compass2, saa_profiles)
    payload2 = build_regime_json_payload(compass2, alloc2, generated_at=FIXED_TS)
    del payload2["generated_at"]
    hash2 = hashlib.sha256(json.dumps(payload2, sort_keys=True).encode()).hexdigest()

    assert hash1 == hash2


def test_pipeline_outputs(tmp_path):
    out = tmp_path / "outputs"
    result = run_compass_pipeline(
        DATA_DIR,
        out,
        positions=load_positions(DATA_DIR / "positions.csv"),
        ticker_targets=load_target_portfolio(DATA_DIR / "target_portfolio.csv"),
        generated_at=FIXED_TS,
    )
    assert (out / "compass_regime.json").exists()
    assert (out / "target_asset_allocation.csv").exists()
    assert (out / "portfolio_gap.csv").exists()
    assert (out / "compass_report.md").exists()
    assert result.allocation.profile == "core_absolute_return"
    assert len(result.group_gaps) == 7

    raw = json.loads((out / "compass_regime.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    assert "computed_market_phase" in raw
    assert "score_breakdown" in raw
    assert "applied_regime" in raw


def test_target_mismatch_warning(market, compass_rules, saa_profiles):
    compass = compute_compass(market, compass_rules)
    allocation = build_portfolio_allocation(compass, saa_profiles)
    targets = load_target_portfolio(DATA_DIR / "target_portfolio.csv")
    warnings = check_target_mismatch(allocation, targets, tolerance_pct=0.5)
    cash_warn = [w for w in warnings if w.asset_group == "cash_short_bond"]
    assert len(cash_warn) >= 1


def test_group_actions_cash_overweight_park(market, compass_rules, saa_profiles):
    from src.compass.group_gap import GroupGapRow

    rows = plan_group_actions(
        [
            GroupGapRow(
                asset_group="cash_short_bond",
                current=44,
                target=37,
                gap=-7,
                action="Hold",
                reason="",
            )
        ],
        applied_regime=RiskRegime.YELLOW_STABLE,
        data_gate="GREEN",
    )
    assert rows[0].action == "Park"


def test_group_actions_crisis_no_buy(market, compass_rules, saa_profiles):
    from src.compass.group_gap import GroupGapRow

    rows = plan_group_actions(
        [
            GroupGapRow(
                asset_group="domestic_beta",
                current=7,
                target=11,
                gap=4,
                action="Hold",
                reason="",
            )
        ],
        applied_regime=RiskRegime.CRISIS,
        data_gate="GREEN",
    )
    assert rows[0].action == "NoTrade"


def test_group_actions_yellow_wait_trigger():
    from src.compass.group_gap import GroupGapRow

    rows = plan_group_actions(
        [
            GroupGapRow(
                asset_group="domestic_beta",
                current=7,
                target=11,
                gap=4,
                action="Hold",
                reason="",
            )
        ],
        applied_regime=RiskRegime.YELLOW_STABLE,
        data_gate="YELLOW",
        buy_triggers_active=True,
    )
    assert rows[0].action == "WaitTrigger"
