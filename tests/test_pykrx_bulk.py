from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data_refresh.pykrx_bulk import (
    SCREEN_MARKETS,
    _compute_returns,
    _merge_universe_frames,
    _turnover_from_ohlcv,
    build_price_row,
    classify_security,
    merge_manual_universe_fields,
    normalize_fundamentals_pit,
    run_kosdaq_universe_sync,
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


def test_turnover_from_ohlcv():
    ohlcv = pd.DataFrame({"종가": [100.0, 200.0], "거래량": [10.0, 5.0]})
    tv = _turnover_from_ohlcv(ohlcv)
    assert tv is not None
    assert list(tv["거래대금"]) == [1000.0, 1000.0]


def test_krx_credentials_missing(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    with pytest.raises(KrxCredentialsError):
        check_krx_credentials()


def test_screen_markets_kospi_only():
    assert SCREEN_MARKETS == ("KOSPI",)
    assert "KOSDAQ" not in SCREEN_MARKETS


def test_merge_universe_drops_kosdaq_leftovers():
    kospi = pd.DataFrame(
        [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]
    )
    existing = pd.DataFrame(
        [
            {"ticker": "005930", "name": "old", "market": "KOSPI"},
            {"ticker": "035760", "name": "CJ ENM", "market": "KOSDAQ"},
        ]
    )
    merged = _merge_universe_frames(existing, kospi, pd.DataFrame())
    markets = set(merged["market"].astype(str).str.upper())
    assert "KOSDAQ" not in markets
    assert "005930" in set(merged["ticker"].map(lambda t: str(t).zfill(6)))


def test_collect_yaml_markets_kospi_only():
    import yaml

    path = Path(__file__).resolve().parents[1] / "alpha_portfolio" / "config" / "collect.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert cfg["collect"]["markets"] == ["KOSPI"]


def test_kosdaq_sync_strips_rows_without_krx(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame(
        [
            {"ticker": "005930", "market": "KOSPI"},
            {"ticker": "035760", "market": "KOSDAQ"},
        ]
    ).to_csv(data / "universe.csv", index=False)
    result = run_kosdaq_universe_sync(data)
    assert result.kosdaq_universe_count == 0
    out = pd.read_csv(data / "universe.csv", dtype=str)
    assert list(out["market"].str.upper()) == ["KOSPI"]
    assert any("생략" in w for w in result.warnings)
