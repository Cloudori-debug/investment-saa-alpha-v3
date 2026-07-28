"""Zero-target asset group buy signal suppression."""
from __future__ import annotations

from pathlib import Path

from src.config import load_trigger_rules
from src.models import MarketIndicators, TriggerAlert, TriggerStatus
from src.trigger_conditions import build_trigger_context, evaluate_asset_triggers

ROOT = Path(__file__).resolve().parents[1]


def test_domestic_beta_buy_suppressed_when_target_zero() -> None:
    market = MarketIndicators(
        date="2026-06-29",
        kospi=8471,
        kospi_recent_high=9114,
        vix=18.6,
        usdkrw=1540,
        regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    market_alerts = [
        TriggerAlert(
            key="kospi_pullback",
            label="KOSPI Pullback",
            status=TriggerStatus.ACTIVE,
            detail="drawdown",
        ),
    ]
    ctx = build_trigger_context(
        market,
        rules,
        market_alerts,
        asset_group_gaps={"domestic_beta": {"target": 0.0, "current": 0.0, "gap": 0.0}},
    )
    alerts = evaluate_asset_triggers(ctx)
    domestic = next(a for a in alerts if a.key == "asset_buy_domestic_beta")
    assert domestic.status == TriggerStatus.WATCH
    assert "watch signal suppressed" in domestic.label
    assert "suppressed" in domestic.detail
