from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.collect.dates import normalize_ticker as nt
from src.collect.pykrx_collector import (
    _build_snapshot_row,
    _compute_price_metrics,
    _is_etf_name,
    filter_liquid_by_cap,
    select_tickers,
)


def test_snapshot_market_cap_missing_is_nan_not_zero():
    """Failed/absent market-cap fetch must stay NaN, never a fabricated 0.0."""
    ohlcv = pd.DataFrame({"종가": [90000, 95000], "거래량": [10, 20]})
    row = _build_snapshot_row("021240", "2026-07-17", ohlcv, cap_hist=None, cap_today=None)
    assert pd.isna(row["market_cap"])  # not 0.0

    cap_today = pd.Series({"시가총액": 0.0})  # zero is treated as missing
    row_zero = _build_snapshot_row("021240", "2026-07-17", ohlcv, None, cap_today)
    assert pd.isna(row_zero["market_cap"])

    cap_ok = pd.Series({"시가총액": 5.0e12})
    row_ok = _build_snapshot_row("021240", "2026-07-17", ohlcv, None, cap_ok)
    assert row_ok["market_cap"] == 5.0e12


def test_normalize_ticker():
    assert nt("2180") == "002180"


def test_is_etf_name():
    assert _is_etf_name("KODEX 200")
    assert not _is_etf_name("코웨이")


def test_compute_price_metrics():
    closes = pd.Series([100, 110, 120, 130, 140, 150] * 30, dtype=float)
    m = _compute_price_metrics(closes)
    assert "return_6m" in m
    assert m["high_52w"] >= m["low_52w"]


def test_select_tickers_holdings(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame(
        {"ticker": ["021240"], "asset_group": ["kr_alpha"], "current_value": [1]}
    ).to_csv(raw / "positions.csv", index=False)
    pd.DataFrame({"ticker": ["021240", "005830"]}).to_csv(raw / "fundamentals.csv", index=False)
    universe = pd.DataFrame(
        {
            "ticker": ["021240", "005830", "069500"],
            "is_etf": ["false", "false", "true"],
            "is_spac": ["false", "false", "false"],
        }
    )
    paths = {"raw": raw}
    tickers = select_tickers(universe, scope="holdings", paths=paths, gate_cfg={}, max_tickers=0)
    assert "021240" in tickers
    assert "005830" in tickers
    assert "069500" not in tickers


def test_select_tickers_liquid(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame({"ticker": ["021240"], "asset_group": ["kr_alpha"], "current_value": [1]}).to_csv(
        raw / "positions.csv", index=False
    )
    pd.DataFrame({"ticker": ["021240"]}).to_csv(raw / "fundamentals.csv", index=False)
    universe = pd.DataFrame(
        {
            "ticker": ["021240", "005930", "000660"],
            "is_etf": ["false", "false", "false"],
            "is_spac": ["false", "false", "false"],
        }
    )
    cap_df = pd.DataFrame(
        {"market_cap": [500e12, 400e12, 80e9]},
        index=["021240", "005930", "000660"],
    )
    paths = {"raw": raw}
    gate_cfg = {"market_cap_min": 300_000_000_000}
    tickers = select_tickers(
        universe,
        scope="liquid",
        paths=paths,
        gate_cfg=gate_cfg,
        max_tickers=0,
        cap_df=cap_df,
        liquid_cfg={"include_holdings": True, "max_tickers": 10},
    )
    assert "021240" in tickers
    assert "005930" in tickers
    assert "000660" not in tickers


def test_filter_liquid_by_cap():
    universe = pd.DataFrame(
        {
            "ticker": ["021240", "005930"],
            "is_etf": ["false", "false"],
            "is_spac": ["false", "false"],
        }
    )
    cap_df = pd.DataFrame({"market_cap": [500e12, 100e9]}, index=["021240", "005930"])
    out = filter_liquid_by_cap(universe, cap_df, {"market_cap_min": 300_000_000_000})
    assert out == ["021240"]


@patch("src.collect.pykrx_collector.import_stock")
def test_run_collect_mock(mock_import, tmp_path):
    from src.collect.pykrx_collector import run_collect
    from src.paths import get_paths

    paths = get_paths(tmp_path)
    for k in ("raw", "config"):
        paths[k].mkdir(parents=True, exist_ok=True)

    (paths["config"] / "collect.yaml").write_text(
        "collect:\n  scope: holdings\n  markets: [KOSPI]\n  enrich_per_pbr: false\n",
        encoding="utf-8",
    )
    (paths["config"] / "universe_gate.yaml").write_text("gate: {}\n", encoding="utf-8")
    pd.DataFrame({"ticker": ["021240"], "asset_group": ["kr_alpha"], "current_value": [1]}).to_csv(
        paths["raw"] / "positions.csv", index=False
    )
    pd.DataFrame({"ticker": ["021240"]}).to_csv(paths["raw"] / "fundamentals.csv", index=False)

    stock = MagicMock()
    stock.get_nearest_business_day_in_a_week.return_value = "20260617"
    stock.get_market_ticker_list.return_value = ["021240"]
    stock.get_market_ticker_name.return_value = "코웨이"
    stock.get_market_ohlcv.return_value = pd.DataFrame(
        {"종가": [90000, 95000], "거래량": [1, 2], "거래대금": [1e9, 2e9]}
    )
    stock.get_market_cap.return_value = pd.DataFrame({"시가총액": [1e12], "거래대금": [1.5e9]})
    stock.get_market_cap_by_ticker.return_value = pd.DataFrame(
        {"시가총액": [1e12], "거래대금": [1.5e9]}, index=["021240"]
    )
    mock_import.return_value = stock

    result = run_collect(tmp_path, as_of="2026-06-17", scope="holdings")
    assert result.snapshot_count == 1
    assert (paths["raw"] / "price_snapshot.csv").exists()
