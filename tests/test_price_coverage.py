from __future__ import annotations

from src.alpha.price_coverage import (
    adjust_gate_for_missing_prices,
    apply_price_coverage_downgrade,
    tickers_missing_prices,
)
from src.alpha.schemas import PriceRecord
from src.hakedaka_gate import eligible_for_proposal_row


def _px(ticker: str) -> PriceRecord:
    return PriceRecord(
        ticker=ticker,
        date="2026-06-24",
        close=1000.0,
        market_cap=5_000_000_000_000,
        trading_value_20d=5_000_000_000,
        trading_value_60d=4_000_000_000,
        return_3m=0.05,
        return_6m=0.1,
        volatility_60d=0.2,
    )


def test_tickers_missing_prices():
    prices = {"005830": _px("005830")}
    missing = tickers_missing_prices({"003080", "005830"}, prices)
    assert missing == {"003080"}


def test_apply_price_coverage_downgrade_blocks_proposal():
    rows = [
        {
            "ticker": "003080",
            "grade": "B",
            "eligible_action": "WATCH",
            "key_reason": "ok",
            "total_score": 56.0,
        },
        {
            "ticker": "005830",
            "grade": "A",
            "eligible_action": "BUY_CANDIDATE",
            "key_reason": "ok",
            "total_score": 70.0,
        },
    ]
    prices = {"005830": _px("005830")}
    out, warnings = apply_price_coverage_downgrade(rows, prices)
    blocked = next(r for r in out if r["ticker"] == "003080")
    allowed = next(r for r in out if r["ticker"] == "005830")
    assert blocked["eligible_action"] == "NO_NEW"
    assert blocked["price_coverage_pass"] is False
    assert not eligible_for_proposal_row(blocked, {})
    assert eligible_for_proposal_row(allowed, {})
    assert any("003080" in w for w in warnings)


def test_adjust_gate_for_missing_prices_yellow():
    status, notes = adjust_gate_for_missing_prices(
        "GREEN", missing_target_tickers=["003080", "008500"],
    )
    assert status == "YELLOW"
    assert notes
