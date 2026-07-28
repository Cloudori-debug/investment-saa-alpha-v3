from __future__ import annotations

from src.models import MarketIndicators
from src.config import load_trigger_rules
from src.trigger_engine import _kospi_pullback_level, _pct_drawdown, evaluate_triggers
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kospi_pullback_trigger():
    recent_high = 100.0
    current = 90.0
    drawdown = _pct_drawdown(current, recent_high)
    assert drawdown == -10.0
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    level = _kospi_pullback_level(drawdown, rules)
    assert level == "buy_2"


def test_vix_normal():
    market = MarketIndicators(
        date="2026-06-17",
        kospi=8801, kospi_recent_high=8933, vix=17.68, usdkrw=1510, regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    alerts = evaluate_triggers(market, rules)
    vix = next(a for a in alerts if a.key == "vix")
    assert vix.status.value == "inactive"


def test_kospi_review_gated_when_dry_run_incomplete():
    market = MarketIndicators(
        date="2026-06-24",
        kospi=8471, kospi_recent_high=9114, vix=18.6, usdkrw=1540, regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    alerts = evaluate_triggers(
        market, rules,
        core_price_gate="pass",
        data_gate="GREEN",
        health_gate="GREEN",
        dry_run_days=3,
    )
    gated = [a for a in alerts if a.key.startswith("kospi_review")]
    assert any(a.key == "kospi_review_gated" for a in gated)
    assert not any(a.status.value == "watch" and "KOSPI_PULLBACK" in a.label for a in gated)


def test_kospi_review_active_when_gates_met():
    market = MarketIndicators(
        date="2026-06-24",
        kospi=8471, kospi_recent_high=9114, vix=18.6, usdkrw=1540, regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    alerts = evaluate_triggers(
        market, rules,
        core_price_gate="pass",
        data_gate="GREEN",
        health_gate="GREEN",
        dry_run_days=10,
    )
    watch = [a for a in alerts if a.key.startswith("kospi_review_") and a.status.value == "watch"]
    assert len(watch) == 1
    assert "PULLBACK_5" in watch[0].key or "PULLBACK" in watch[0].label
