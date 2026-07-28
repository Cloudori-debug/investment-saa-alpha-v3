from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.benchmark_data import ticker_return_mtd, ticker_return_mtd_detail
from src.alpha.nav_log import (
    append_portfolio_nav_log,
    detect_nav_capital_like_events,
    nav_return_mtd,
    nav_return_mtd_detail,
)


def test_nav_return_mtd_stable_period(tmp_path: Path) -> None:
    log = tmp_path / "portfolio_nav_log.csv"
    append_portfolio_nav_log(log, {
        "date": "2026-06-01", "run_id": "r1", "total_nav_krw": 100_000_000,
        "cash_krw": 0, "positions_value_krw": 100_000_000,
        "kr_alpha_value_krw": 0, "core_reference_held_krw": 0, "satellite_other_krw": 0,
    })
    append_portfolio_nav_log(log, {
        "date": "2026-06-26", "run_id": "r2", "total_nav_krw": 102_000_000,
        "cash_krw": 0, "positions_value_krw": 102_000_000,
        "kr_alpha_value_krw": 0, "core_reference_held_krw": 0, "satellite_other_krw": 0,
    })
    assert nav_return_mtd(log, "2026-06-26") == 2.0
    detail = nav_return_mtd_detail(log, "2026-06-26")
    assert detail["raw_nav_return_mtd"] == 2.0
    assert detail["adjusted_nav_return_mtd"] == 2.0
    assert detail["capital_like_events"] == []


def test_nav_capital_registration_jump_adjusted(tmp_path: Path) -> None:
    """Reproduce 2026-07-03 style core_reference registration jump."""
    log = tmp_path / "portfolio_nav_log.csv"
    append_portfolio_nav_log(log, {
        "date": "2026-07-01", "run_id": "a", "total_nav_krw": 91_000_000,
        "cash_krw": 18_000_000, "positions_value_krw": 73_000_000,
        "kr_alpha_value_krw": 39_000_000, "core_reference_held_krw": 23_000_000,
        "satellite_other_krw": 11_000_000,
    })
    append_portfolio_nav_log(log, {
        "date": "2026-07-03", "run_id": "b", "total_nav_krw": 120_000_000,
        "cash_krw": 18_000_000, "positions_value_krw": 102_000_000,
        "kr_alpha_value_krw": 39_300_000, "core_reference_held_krw": 52_000_000,
        "satellite_other_krw": 11_200_000,
    })
    events = detect_nav_capital_like_events([
        {"date": "2026-07-01", "total_nav_krw": "91000000", "cash_krw": "18000000",
         "kr_alpha_value_krw": "39000000", "core_reference_held_krw": "23000000",
         "satellite_other_krw": "11000000"},
        {"date": "2026-07-03", "total_nav_krw": "120000000", "cash_krw": "18000000",
         "kr_alpha_value_krw": "39300000", "core_reference_held_krw": "52000000",
         "satellite_other_krw": "11200000"},
    ])
    assert len(events) == 1
    assert events[0]["estimated_external_flow_krw"] > 20_000_000

    detail = nav_return_mtd_detail(log, "2026-07-03")
    assert detail["raw_nav_return_mtd"] is not None
    assert detail["raw_nav_return_mtd"] > 20
    assert detail["adjusted_nav_return_mtd"] is not None
    assert detail["adjusted_nav_return_mtd"] < 5
    assert nav_return_mtd(log, "2026-07-03") == detail["adjusted_nav_return_mtd"]


def test_ticker_return_mtd_stale_is_none_not_zero() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-26"), "ticker": "069500", "close": 137380.0},
    ])
    detail = ticker_return_mtd_detail(prices, "069500", "2026-07-08")
    assert detail["return_mtd"] is None
    assert detail["quality"] in {"stale_price", "insufficient_history"}
    assert ticker_return_mtd(prices, "069500", "2026-07-08") is None


def test_ticker_return_mtd_ok_series() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-30"), "ticker": "069500", "close": 100.0},
        {"date": pd.Timestamp("2026-07-01"), "ticker": "069500", "close": 100.0},
        {"date": pd.Timestamp("2026-07-08"), "ticker": "069500", "close": 105.0},
    ])
    ret = ticker_return_mtd(prices, "069500", "2026-07-08")
    assert ret == 5.0
