from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.backfill_price_history import (
    _append_only_merge,
    _ohlcv_to_rows,
    backfill_price_history,
    resolve_backfill_tickers,
)


class _FakeStock:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.calls: list[tuple[str, str, str]] = []

    def get_market_ohlcv(self, start: str, end: str, ticker: str):
        self.calls.append((start, end, ticker))
        return self.frames.get(ticker, pd.DataFrame())


def test_resolve_backfill_tickers_includes_benchmark_and_excludes_alpha_cash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n"
        "360750,US,global_beta,core,us,10,0,20\n"
        "000660,SKH,kr_alpha,semi,a,5,0,10\n"
        "CASH,cash,cash_short_bond,cash,cash,5,0,10\n",
        encoding="utf-8",
    )
    tickers = resolve_backfill_tickers(data)
    assert "069500" in tickers
    assert "360750" in tickers
    assert "000660" not in tickers
    assert "CASH" not in tickers


def test_append_only_does_not_overwrite(tmp_path: Path) -> None:
    hist = tmp_path / "prices_history.csv"
    hist.write_text(
        "date,ticker,close,market_cap,trading_value_20d,trading_value_60d,"
        "return_1m,return_3m,return_6m,return_12m,return_12m_ex_1m,high_52w,"
        "distance_from_52w_high,volatility_60d\n"
        "2026-06-26,069500,100,0,0,0,0,0,0,0,0,100,0,0\n",
        encoding="utf-8-sig",
    )
    existing = {("069500", "2026-06-26")}
    rows = [
        {"date": "2026-06-26", "ticker": "069500", "close": 999, "market_cap": 0,
         "trading_value_20d": 0, "trading_value_60d": 0, "return_1m": 0, "return_3m": 0,
         "return_6m": 0, "return_12m": 0, "return_12m_ex_1m": 0, "high_52w": 999,
         "distance_from_52w_high": 0, "volatility_60d": 0},
        {"date": "2026-07-01", "ticker": "069500", "close": 110, "market_cap": 0,
         "trading_value_20d": 0, "trading_value_60d": 0, "return_1m": 0, "return_3m": 0,
         "return_6m": 0, "return_12m": 0, "return_12m_ex_1m": 0, "high_52w": 110,
         "distance_from_52w_high": 0, "volatility_60d": 0},
    ]
    added, skipped = _append_only_merge(hist, rows, existing)
    assert added == 1
    assert skipped == 1
    df = pd.read_csv(hist, dtype={"ticker": str})
    old = df[(df["ticker"] == "069500") & (df["date"] == "2026-06-26")]
    assert int(old.iloc[0]["close"]) == 100  # not overwritten


def test_backfill_mock_no_network(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n"
        "360750,US,global_beta,core,us,10,0,20\n",
        encoding="utf-8",
    )
    idx = pd.to_datetime(["2026-06-17", "2026-06-26", "2026-07-08"])
    frame = pd.DataFrame({"종가": [100.0, 105.0, 110.0]}, index=idx)
    stock = _FakeStock({"069500": frame, "360750": frame})
    report = backfill_price_history(
        data,
        tickers=["069500", "360750"],
        as_of="2026-07-08",
        lookback_days=30,
        output_dir=out,
        dry_run=False,
        sleep_sec=0,
        stock=stock,
    )
    assert report["success"] is True
    assert report["krx_login_status"] == "injected"
    assert report["rows_added"] == 6
    # idempotent second run
    report2 = backfill_price_history(
        data,
        tickers=["069500", "360750"],
        as_of="2026-07-08",
        lookback_days=30,
        output_dir=out,
        sleep_sec=0,
        stock=stock,
    )
    assert report2["rows_added"] == 0
    assert report2["rows_skipped_existing"] == 6


def test_credentials_missing_soft_fail(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()

    def _boom(_data_dir=None):
        from src.data_refresh.pykrx_client import KrxCredentialsError

        raise KrxCredentialsError("missing")

    monkeypatch.setattr("scripts.backfill_price_history.import_pykrx_stock", _boom)
    report = backfill_price_history(
        data,
        tickers=["069500"],
        as_of="2026-07-08",
        output_dir=out,
        dry_run=False,
    )
    assert report["success"] is False
    assert report["reason"] == "krx_credentials_missing"
    assert (out / "price_backfill_report.json").exists()
