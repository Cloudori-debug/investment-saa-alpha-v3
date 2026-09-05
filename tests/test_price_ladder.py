"""Five-rung price ladder: 하한→상한 equal ticks, fill = current."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.price_ladder import (
    LookbackLow,
    attach_ladder_extra,
    build_price_ladder,
    load_lookback_lows,
)


def test_five_equal_rungs_and_mid_fill() -> None:
    ladder = build_price_ladder(current=150, high=200, low=100, high_source="approved")
    assert ladder.ok
    assert ladder.rungs == (100.0, 125.0, 150.0, 175.0, 200.0)
    assert ladder.labels == ("매수1", "매수2", "줄이기", "절반", "전량")
    assert ladder.fill_pct == 50.0
    assert ladder.over_high is False
    assert ladder.under_low is False


def test_current_above_high_fills_100() -> None:
    ladder = build_price_ladder(current=250, high=200, low=100)
    assert ladder.ok
    assert ladder.fill_pct == 100.0
    assert ladder.over_high is True


def test_current_below_low_fills_0() -> None:
    ladder = build_price_ladder(current=80, high=200, low=100)
    assert ladder.ok
    assert ladder.fill_pct == 0.0
    assert ladder.under_low is True


def test_high_not_greater_than_low_is_not_ok() -> None:
    assert build_price_ladder(current=100, high=90, low=100).ok is False
    assert build_price_ladder(current=100, high=None, low=50).ok is False


def test_attach_uses_quant_mid_when_no_approved_target() -> None:
    extra = attach_ladder_extra(
        {"quant_price_mid": 45000},
        ticker="000001",
        current=30000,
        target_price=None,
        lookback_lows={"000001": LookbackLow(20000.0, "low_52w")},
    )
    assert extra["ladder_ok"] is True
    assert extra["ladder_high"] == 45000.0
    assert extra["ladder_high_source"] == "quant_draft"
    assert extra["ladder_low"] == 20000.0


def test_load_lookback_prefers_52w_when_history_thin(tmp_path: Path) -> None:
    snap_dir = tmp_path / "alpha_portfolio" / "data" / "raw"
    snap_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "ticker": ["000070"],
            "low_52w": [51900],
            "high_52w": [74500],
            "close": [60900],
        }
    ).to_csv(snap_dir / "price_snapshot.csv", index=False)
    prices = pd.DataFrame(
        {
            "date": ["2026-06-24", "2026-08-28"],
            "ticker": ["000070", "000070"],
            "close": [58000, 60900],
        }
    )
    lows = load_lookback_lows(tmp_path, prices)
    assert lows["000070"].source == "low_52w"
    assert lows["000070"].price == 51900.0
    # 52w high must not become the floor
    assert lows["000070"].price != 74500.0


def test_load_lookback_uses_120d_when_history_thick(tmp_path: Path) -> None:
    rows = []
    for i in range(25):
        rows.append({"date": f"2026-07-{i+1:02d}", "ticker": "000070", "close": 50000 + i * 100})
    prices = pd.DataFrame(rows)
    lows = load_lookback_lows(tmp_path, prices)
    assert lows["000070"].source == "120d"
    assert lows["000070"].price == 50000.0
