"""ECONOMIC_COMPASS phase 0–1 — tilt scale + regime/phase hysteresis."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.compass.hysteresis import apply_regime_hysteresis
from src.compass.judgment_log import read_judgment_log_tail, write_compass_judgment_log
from src.compass.models import RiskRegime
from src.compass.portfolio_builder import build_portfolio_allocation, resolve_taa_tilt_scale
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.config import load_yaml
from src.data_loader import load_market_indicators

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def market():
    return load_market_indicators(DATA_DIR / "market_indicators.csv")


@pytest.fixture
def rules():
    return load_yaml(DATA_DIR / "compass_rules.yaml")


@pytest.fixture
def profiles():
    return load_saa_profiles(DATA_DIR / "saa_profiles.yaml")


def test_tilt_scale_defaults_to_1_without_governance():
    assert resolve_taa_tilt_scale(None) == 1.0
    assert resolve_taa_tilt_scale({}) == 1.0
    assert resolve_taa_tilt_scale({"tilt_governance": {}}) == 1.0


def test_tilt_scale_shrinks_recorded_tilts(market, rules, profiles):
    market.regime = "CRISIS"
    compass = compute_compass(market, rules)  # no history → bootstrap
    meta_full: dict = {}
    meta_scaled: dict = {}
    alloc_full = build_portfolio_allocation(
        compass, profiles, rules={"tilt_governance": {"taa_tilt_scale": 1.0}}, tilt_meta=meta_full,
    )
    alloc_scaled = build_portfolio_allocation(
        compass, profiles, rules={"tilt_governance": {"taa_tilt_scale": 0.4}}, tilt_meta=meta_scaled,
    )
    cash_full = next(g for g in alloc_full.groups if g.asset_group == "cash_short_bond")
    cash_scaled = next(g for g in alloc_scaled.groups if g.asset_group == "cash_short_bond")
    # Scaled tilt magnitude toward cash should be smaller than full scale (both relative to SAA).
    assert abs(cash_scaled.regime_tilt) <= abs(cash_full.regime_tilt) + 1e-9
    assert meta_scaled["taa_tilt_scale"] == 0.4
    raw = meta_scaled["raw_regime_tilt"]["cash_short_bond"]
    scaled = meta_scaled["scaled_regime_tilt"]["cash_short_bond"]
    assert abs(scaled - raw * 0.4) < 1e-6


def test_hysteresis_holds_one_day_regime_spike(market, rules):
    rules = deepcopy(rules)
    rules["hysteresis"] = {"regime_confirm_runs": 2, "phase_confirm_runs": 2}
    history = [
        {
            "computed_regime": "YELLOW_STABLE",
            "applied_regime": "YELLOW_STABLE",
            "market_phase": "MARKET_RECOVERY",
            "computed_market_phase": "MARKET_RECOVERY",
        }
    ]

    spiked = deepcopy(market)
    spiked.regime = "NEUTRAL"
    spiked.vix = 26.0  # RISK_OFF under default rules, below CRISIS
    spiked.kospi = 2500.0
    spiked.kospi_recent_high = 2600.0  # mild DD — avoid CRISIS drawdown path
    spiked.kospi_200ma = 2400.0
    day1 = compute_compass(spiked, rules, judgment_history=history, use_manual_regime=False)
    assert day1.computed_regime == RiskRegime.RISK_OFF
    assert day1.applied_regime == RiskRegime.YELLOW_STABLE  # hold previous
    assert day1.hysteresis_note and "pending" in (day1.hysteresis_note or "")

    history2 = history + [
        {
            "computed_regime": day1.computed_regime.value,
            "applied_regime": day1.applied_regime.value,
            "market_phase": day1.market_phase.value,
            "computed_market_phase": (day1.computed_market_phase or day1.market_phase).value,
        }
    ]
    day2 = compute_compass(spiked, rules, judgment_history=history2, use_manual_regime=False)
    assert day2.computed_regime == RiskRegime.RISK_OFF
    assert day2.applied_regime == RiskRegime.RISK_OFF  # confirmed after 2 runs


def test_crisis_entry_skips_hysteresis(market, rules):
    rules = deepcopy(rules)
    rules["hysteresis"] = {"regime_confirm_runs": 2, "phase_confirm_runs": 2}
    history = [
        {
            "computed_regime": "YELLOW_STABLE",
            "applied_regime": "YELLOW_STABLE",
            "market_phase": "MARKET_RECOVERY",
            "computed_market_phase": "MARKET_RECOVERY",
        }
    ]
    crisis_m = deepcopy(market)
    crisis_m.regime = "NEUTRAL"
    crisis_m.vix = 35.0
    result = compute_compass(crisis_m, rules, judgment_history=history, use_manual_regime=False)
    assert result.computed_regime == RiskRegime.CRISIS
    assert result.applied_regime == RiskRegime.CRISIS
    assert result.hysteresis_note and "crisis_entry_immediate" in result.hysteresis_note


def test_apply_regime_hysteresis_crisis_exit_needs_confirm():
    rules = {"hysteresis": {"regime_confirm_runs": 2}}
    history = [
        {"computed_regime": "CRISIS", "applied_regime": "CRISIS"},
    ]
    applied, note = apply_regime_hysteresis(RiskRegime.YELLOW_STABLE, history, rules)
    assert applied == RiskRegime.CRISIS
    assert note == "crisis_exit_pending"

    history2 = history + [
        {"computed_regime": "YELLOW_STABLE", "applied_regime": "CRISIS"},
    ]
    applied2, note2 = apply_regime_hysteresis(RiskRegime.YELLOW_STABLE, history2, rules)
    assert applied2 == RiskRegime.YELLOW_STABLE
    assert note2 == "crisis_exit_confirmed"


def test_judgment_log_schema_fields(market, rules, tmp_path):
    compass = compute_compass(market, rules)
    meta = {
        "taa_tilt_scale": 0.4,
        "raw_phase_tilt": {"kr_alpha": 1.0},
        "raw_regime_tilt": {"kr_alpha": 0.0},
        "scaled_phase_tilt": {"kr_alpha": 0.4},
        "scaled_regime_tilt": {"kr_alpha": 0.0},
    }
    path = write_compass_judgment_log(tmp_path, compass, market, tilt_meta=meta, run_id="t1")
    rows = read_judgment_log_tail(path, n=1)
    assert len(rows) == 1
    row = rows[0]
    for key in (
        "date", "run_id", "growth_score", "inflation_score", "liquidity_score",
        "risk_appetite_score", "market_phase", "computed_market_phase", "phase_confidence",
        "computed_regime", "applied_regime", "regime_confidence", "override_active",
        "compass_direction", "taa_tilt_scale", "raw_phase_tilt", "raw_regime_tilt",
        "scaled_phase_tilt", "scaled_regime_tilt", "market_inputs",
    ):
        assert key in row
    assert "vix" in row["market_inputs"]
