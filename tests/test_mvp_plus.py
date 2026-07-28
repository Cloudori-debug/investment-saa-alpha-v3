from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.compass.economic_phase import score_growth
from src.config import load_trigger_rules, load_yaml
from src.data_refresh.external_market import fetch_external_market
from src.models import MarketIndicators
from src.trigger_engine import evaluate_triggers
from src.unified_data_gate import effective_data_gate, merge_data_gates

ROOT = Path(__file__).resolve().parents[1]


def test_merge_data_gates_conservative():
    assert merge_data_gates("GREEN", "YELLOW") == "YELLOW"
    assert merge_data_gates("GREEN", "RED") == "RED"
    assert effective_data_gate("GREEN", "YELLOW") == "YELLOW"


def test_asset_triggers_emits_asset_alerts():
    market = MarketIndicators(
        date="2026-06-17",
        kospi=8000,
        kospi_recent_high=8933,
        vix=17,
        usdkrw=1490,
        regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    alerts = evaluate_triggers(market, rules, asset_group_gaps={"domestic_beta": {"gap": 3}})
    keys = {a.key for a in alerts}
    assert "kospi_pullback" in keys
    assert any(k.startswith("asset_") for k in keys)


def test_sp500_compass_growth_score():
    rules = load_yaml(ROOT / "data" / "compass_rules.yaml")
    base = MarketIndicators(
        date="2026-06-17", kospi=8801, kospi_recent_high=8933, kospi_200ma=7724,
        vix=17, usdkrw=1510, regime="NEUTRAL", foreign_flow_3d="neutral",
    )
    with_sp = base.model_copy(update={"sp500": 5500, "sp500_recent_high": 5600})
    s0, _, _ = score_growth(base, rules)
    s1, _, bd = score_growth(with_sp, rules)
    assert s1 != s0 or any(b.indicator == "sp500_drawdown" for b in bd)


@patch("src.data_refresh.external_market._fetch_yahoo_chart")
def test_fetch_external_market_mock(mock_chart):
    closes = [(i, 100.0 + i * 0.1) for i in range(250)]
    mock_chart.return_value = closes
    result = fetch_external_market(as_of="2026-06-17")
    assert result.as_of == "2026-06-17"
    assert "sp500" in result.series or result.fx_usdkrw is not None
