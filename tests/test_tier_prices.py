from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.schemas import UniverseRecord
from src.alpha.universe_filter import filter_universe
from src.data_refresh.price_store import merge_prices_dataframes
from src.data_refresh.prices_refresh import collect_tier_a_tickers, fetch_and_merge_missing_prices


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_merge_prices_keeps_latest_per_ticker():
    existing = pd.DataFrame([
        {"date": "2026-06-01", "ticker": "005930", "close": "100"},
        {"date": "2026-06-01", "ticker": "000660", "close": "200"},
    ])
    new = pd.DataFrame([
        {"date": "2026-06-17", "ticker": "005930", "close": "110"},
        {"date": "2026-06-17", "ticker": "035420", "close": "300"},
    ])
    merged = merge_prices_dataframes(existing, new)
    by_ticker = dict(zip(merged["ticker"], merged["close"], strict=False))
    assert by_ticker["005930"] == "110"
    assert by_ticker["000660"] == "200"
    assert by_ticker["035420"] == "300"
    assert len(merged) == 3


def test_collect_tier_a_includes_positions_and_target(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([
        {
            "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
            "sector": "insurance", "style": "", "quantity": "47", "current_value": "1000000",
            "avg_price": "", "current_price": "139000",
        },
    ]).to_csv(data / "positions.csv", index=False)
    pd.DataFrame([
        {
            "ticker": "005440", "name": "현대그린푸드", "asset_group": "kr_alpha",
            "target_weight": "2", "min_weight": "0", "max_weight": "5",
            "sector": "food", "role": "",
        },
    ]).to_csv(data / "target_portfolio.csv", index=False)

    tickers = collect_tier_a_tickers(data, top_n=0)
    assert "005830" in tickers
    assert "005440" in tickers
    assert "CASH" not in tickers


def test_fetch_and_merge_refresh_existing_updates_date(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([
        {"date": "2026-06-23", "ticker": "005830", "close": "100", "market_cap": "1"},
    ]).to_csv(data / "prices.csv", index=False)

    fetched = pd.DataFrame([
        {
            "date": "2026-06-26", "ticker": "005830", "close": "200", "market_cap": "2",
            "trading_value_20d": "3", "trading_value_60d": "4",
            "return_1m": "0", "return_3m": "0", "return_6m": "0", "return_12m": "0",
            "return_12m_ex_1m": "0", "high_52w": "0", "distance_from_52w_high": "0",
            "volatility_60d": "0",
        },
    ])

    monkeypatch.setattr(
        "src.data_refresh.pykrx_bulk.fetch_prices_for_tickers",
        lambda stock, tickers, as_of_date: fetched.copy(),
    )
    monkeypatch.setattr(
        "src.data_refresh.pykrx_client.import_pykrx_stock",
        lambda data_dir: object(),
    )
    monkeypatch.setattr(
        "src.data_refresh.pykrx_client.resolve_trading_date",
        lambda stock, as_of: as_of,
    )

    from src.data_refresh.prices_refresh import fetch_and_merge_prices

    refreshed, warnings = fetch_and_merge_prices(
        data, ["005830"], "2026-06-26", only_missing=False,
    )
    assert refreshed == ["005830"]
    out = pd.read_csv(data / "prices.csv", dtype=str)
    row = out[out["ticker"] == "005830"].iloc[0]
    assert row["date"] == "2026-06-26"
    assert row["close"] == "200"
    assert not warnings


def test_fetch_and_merge_appends_without_dropping(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([
        {"date": "2026-06-01", "ticker": "005830", "close": "100", "market_cap": "1"},
    ]).to_csv(data / "prices.csv", index=False)

    fetched = pd.DataFrame([
        {
            "date": "2026-06-17", "ticker": "005440", "close": "200", "market_cap": "2",
            "trading_value_20d": "3", "trading_value_60d": "4",
            "return_1m": "0", "return_3m": "0", "return_6m": "0", "return_12m": "0",
            "return_12m_ex_1m": "0", "high_52w": "0", "distance_from_52w_high": "0",
            "volatility_60d": "0",
        },
    ])

    monkeypatch.setattr(
        "src.data_refresh.pykrx_bulk.fetch_prices_for_tickers",
        lambda stock, tickers, as_of_date: fetched.copy(),
    )
    monkeypatch.setattr(
        "src.data_refresh.pykrx_client.import_pykrx_stock",
        lambda data_dir: object(),
    )
    monkeypatch.setattr(
        "src.data_refresh.pykrx_client.resolve_trading_date",
        lambda stock, as_of: as_of,
    )

    added, warnings = fetch_and_merge_missing_prices(data, ["005440"], "2026-06-17")
    assert added == ["005440"]
    out = pd.read_csv(data / "prices.csv", dtype=str)
    assert set(out["ticker"]) == {"005830", "005440"}
    assert not warnings


def test_load_prices_latest_per_ticker_with_partial_as_of(tmp_path):
    from src.alpha.loaders import load_prices

    path = tmp_path / "prices.csv"
    pd.DataFrame([
        {"date": "2026-06-23", "ticker": "005930", "close": "100"},
        {"date": "2026-06-23", "ticker": "000660", "close": "200"},
        {"date": "2026-06-24", "ticker": "005930", "close": "110"},
    ]).to_csv(path, index=False)
    rows = load_prices(path, as_of="2026-06-24")
    by_ticker = {r.ticker: r.close for r in rows}
    assert by_ticker["005930"] == 110.0
    assert by_ticker["000660"] == 200.0


def test_load_alpha_top_tickers_skips_empty_csv(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "alpha_shortlist.csv").write_text("", encoding="utf-8")
    (out / "alpha_candidates.csv").write_text("\n", encoding="utf-8")
    from src.data_refresh.prices_refresh import _load_alpha_top_tickers

    assert _load_alpha_top_tickers(out, top_n=50) == []


def test_write_alpha_candidates_empty_has_header(tmp_path):
    from src.alpha.alpha_report import write_alpha_candidates

    path = tmp_path / "alpha_candidates.csv"
    write_alpha_candidates(path, [])
    df = pd.read_csv(path, dtype=str)
    assert "ticker" in df.columns
    assert len(df) == 0
    from src.alpha.loaders import load_universe_filter_config

    cfg = load_universe_filter_config(DATA_DIR / "universe_filter.yaml")
    universe = [
        UniverseRecord(ticker="999888", name="시세없음", listed_date="2010-01-01"),
    ]
    passed, excluded = filter_universe(universe, {}, cfg, "2026-06-17")
    assert not passed
    assert excluded[0].failed_rule == "missing_price"
