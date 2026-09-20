from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.collect.dates import normalize_ticker as nt
from src.collect.pykrx_collector import (
    _build_snapshot_row,
    _compute_price_metrics,
    _is_etf_name,
    apply_market_cap_to_snapshot,
    fetch_kospi_market_cap,
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


def test_screen_markets_one_book_at_a_time():
    from src.collect.pykrx_collector import _screen_markets
    from src.paths import get_paths

    assert _screen_markets(["KOSPI", "KOSDAQ"]) == ["KOSPI"]
    assert _screen_markets(None) == ["KOSPI"]
    assert _screen_markets(["KOSDAQ"]) == ["KOSPI"]
    assert _screen_markets(["KOSPI"], book="KOSDAQ") == ["KOSDAQ"]
    assert _screen_markets(["KOSDAQ"], book="KOSDAQ") == ["KOSDAQ"]
    kq = get_paths(Path("/tmp/alpha_portfolio"), book="KOSDAQ")
    kp = get_paths(Path("/tmp/alpha_portfolio"), book="KOSPI")
    assert "books" in str(kq["raw"]).replace("\\", "/")
    assert "books" not in str(kp["raw"]).replace("\\", "/")
    assert kq["raw"] != kp["raw"]


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


def test_liquid_stub_does_not_invent_roe(tmp_path: Path):
    from src.collect.liquid_fundamentals import (
        fill_sector_relative_multiples,
        sync_liquid_fundamentals_stubs,
    )

    snap = pd.DataFrame(
        {
            "ticker": ["247540", "086520", "196170"],
            "market_cap": [1e13, 9e12, 8e12],
            "avg_trading_value_20d": [5e10, 5e10, 5e10],
        }
    )
    universe = pd.DataFrame(
        {
            "ticker": ["247540", "086520", "196170"],
            "name": ["에코프로비엠", "에코프로", "알테오젠"],
            "sector": ["전기·전자", "금융", "일반서비스"],
        }
    )
    path = tmp_path / "fundamentals.csv"
    n, _ = sync_liquid_fundamentals_stubs(
        path,
        snap,
        universe,
        as_of="2026-09-04",
        gate_cfg={"market_cap_min": 1, "avg_trading_value_20d_min": 1},
        max_stubs=10,
    )
    assert n == 3
    df = pd.read_csv(path, dtype=str)
    assert (df["source"] == "liquid_stub").all()
    assert df["roe"].fillna("").str.strip().eq("").all()
    df["pbr"] = [1.2, 2.4, 3.6]
    df["sector"] = ["a", "a", "a"]
    filled = fill_sector_relative_multiples(df)
    assert float(filled["sector_pbr_median"].iloc[0]) == pytest.approx(2.4)


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


def test_kosdaq_sector_relative_keeps_small_sector_leader():
    mega = [f"{i:06d}" for i in range(1, 9)]
    small = "000099"
    universe = pd.DataFrame(
        {
            "ticker": mega + [small],
            "name": ["M"] * 8 + ["S"],
            "sector": ["전기·전자"] * 8 + ["제약"],
            "market": ["KOSDAQ"] * 9,
            "is_etf": ["false"] * 9,
            "is_spac": ["false"] * 9,
        }
    )
    caps = {t: float(900 - i * 10) * 1e9 for i, t in enumerate(mega)}
    caps[small] = 250e9
    cap_df = pd.DataFrame({"market_cap": pd.Series(caps)})
    gate = {"market_cap_min": 200e9}

    overall = filter_liquid_by_cap(
        universe, cap_df, gate, max_tickers=5, markets=["KOSDAQ"]
    )
    assert small not in overall
    assert overall == mega[:5]

    mixed = filter_liquid_by_cap(
        universe,
        cap_df,
        gate,
        max_tickers=5,
        markets=["KOSDAQ"],
        sector_top_n=2,
    )
    assert small in mixed
    assert mixed.count(small) == 1
    assert len([t for t in mixed if t in mega]) == 2
    assert len(mixed) == 3


def test_snapshot_avg20_from_ohlcv_when_cap_hist_missing():
    ohlcv = pd.DataFrame(
        {"종가": [100.0, 110.0, 120.0], "거래량": [10.0, 20.0, 30.0]}
    )
    row = _build_snapshot_row("005930", "2026-08-28", ohlcv, cap_hist=None, cap_today=None)
    assert row["avg_trading_value_20d"] == 120.0 * 30.0


@patch("src.collect.pykrx_collector.time.sleep", lambda *_a, **_k: None)
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
    snap = pd.read_csv(paths["raw"] / "price_snapshot.csv")
    assert float(snap.loc[0, "market_cap"]) == 1e12
    stock.get_market_cap.assert_not_called()


def test_fetch_kospi_market_cap_skips_empty_then_uses_prior_day():
    stock = MagicMock()
    friday = pd.DataFrame({"시가총액": [1.0e12]}, index=["005930"])
    stock.get_market_cap_by_ticker.side_effect = [pd.DataFrame(), friday]
    cap_df, used = fetch_kospi_market_cap(stock, "2026-08-29", lookback_days=5, pause_sec=0)
    assert used == "2026-08-28"
    assert float(cap_df.loc["005930", "시가총액"]) == 1.0e12


def test_apply_market_cap_to_snapshot_normalizes_ticker():
    snap = pd.DataFrame({"ticker": ["005930"], "market_cap": [float("nan")]})
    cap = pd.DataFrame({"시가총액": [4.0e14]}, index=["5930"])
    out = apply_market_cap_to_snapshot(snap, cap)
    assert float(out.loc[0, "market_cap"]) == 4.0e14


@patch("src.collect.pykrx_collector.time.sleep", lambda *_a, **_k: None)
@patch("src.collect.pykrx_collector.import_stock")
def test_run_collect_raises_when_kospi_cap_empty(mock_import, tmp_path):
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
    stock.get_nearest_business_day_in_a_week.return_value = "20260828"
    stock.get_market_ticker_list.return_value = ["021240"]
    stock.get_market_ticker_name.return_value = "코웨이"
    stock.get_market_cap_by_ticker.return_value = pd.DataFrame()
    mock_import.return_value = stock

    with pytest.raises(RuntimeError, match="시가총액 조회 실패"):
        run_collect(tmp_path, as_of="2026-08-29", scope="holdings")
