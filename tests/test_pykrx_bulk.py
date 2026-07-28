from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data_refresh.pykrx_bulk import (
    _compute_returns,
    build_price_row,
    classify_security,
    merge_manual_universe_fields,
    normalize_fundamentals_pit,
    select_tickers_for_prices,
)
from src.data_refresh.pykrx_client import KrxCredentialsError, check_krx_credentials


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_classify_preferred_and_etf():
    etf = classify_security("KODEX 200", "069500", {"069500"}, set())
    assert etf["is_etf_etn"] is True
    assert etf["security_type"] == "etf_etn"

    pref = classify_security("삼성전자우", "005935", set(), set())
    assert pref["is_preferred"] is True
    assert pref["security_type"] == "preferred_stock"

    common = classify_security("삼성전자", "005930", set(), set())
    assert common["security_type"] == "common_stock"


def test_compute_returns():
    idx = pd.date_range("2025-01-01", periods=300, freq="B")
    closes = pd.Series(range(100, 400), index=idx, dtype=float)
    rets = _compute_returns(closes)
    assert "return_3m" in rets
    assert "volatility_60d" in rets
    assert rets["return_3m"] > 0


def test_build_price_row():
    idx = pd.date_range("2025-01-01", periods=80, freq="B")
    ohlcv = pd.DataFrame({"종가": range(100, 180)}, index=idx)
    cap_hist = pd.DataFrame({"거래대금": [1_000_000_000] * 80}, index=idx)
    cap_today = pd.Series({"시가총액": 5_000_000_000_000, "거래대금": 2_000_000_000})
    row = build_price_row("005930", "2026-06-17", ohlcv, cap_hist, cap_today)
    assert row["ticker"] == "005930"
    assert row["trading_value_20d"] > 0


def test_merge_manual_universe_fields():
    existing = pd.DataFrame([
        {
            "ticker": "005830",
            "name": "DB손해보험",
            "market": "KOSPI",
            "security_type": "common_stock",
            "sector": "insurance",
            "industry": "insurance",
            "listed_date": "1999-03-15",
            "is_preferred": "false",
            "is_etf_etn": "false",
            "is_reit": "false",
            "is_spac": "false",
            "is_trading_halt": "true",
            "is_administrative_issue": "false",
            "audit_opinion": "clean",
            "capital_impairment": "false",
        }
    ])
    new = existing.copy()
    new["is_trading_halt"] = "false"
    merged = merge_manual_universe_fields(existing, new)
    assert merged.iloc[0]["is_trading_halt"] == "true"


def test_merge_manual_preserves_new_audit_when_old_empty():
    existing = pd.DataFrame([
        {
            "ticker": "005930",
            "audit_opinion": "",
            "is_trading_halt": "false",
        }
    ])
    new = pd.DataFrame([
        {
            "ticker": "005930",
            "audit_opinion": "clean",
            "is_trading_halt": "false",
        }
    ])
    merged = merge_manual_universe_fields(existing, new)
    assert merged.iloc[0]["audit_opinion"] == "clean"


def test_normalize_fundamentals_pit():
    df = pd.DataFrame([
        {"ticker": "005930", "report_date": "2026-03-31", "usable_from_date": "2026-06-18"},
        {"ticker": "000660", "report_date": "2026-03-31", "usable_from_date": ""},
    ])
    out = normalize_fundamentals_pit(df)
    assert out.iloc[0]["usable_from_date"] == "2026-03-31"
    assert out.iloc[1]["usable_from_date"] == "2026-03-31"


def test_select_tickers_holdings_scope():
    universe = pd.read_csv(DATA_DIR / "universe.csv", dtype=str, keep_default_na=False)
    cap = pd.DataFrame(
        {"시가총액": [500_000_000_000], "거래대금": [2_000_000_000]},
        index=["005830"],
    )
    tickers = select_tickers_for_prices(
        universe, cap, scope="holdings", data_dir=DATA_DIR, max_tickers=20
    )
    assert len(tickers) >= 1


def test_krx_credentials_missing(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    with pytest.raises(KrxCredentialsError):
        check_krx_credentials()
