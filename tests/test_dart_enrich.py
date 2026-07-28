from __future__ import annotations

from unittest.mock import patch

import pytest

from src.data_refresh.dart_client import DartCredentialsError, get_dart_api_key
from src.data_refresh.dart_financials import (
    ReportMeta,
    _parse_amount,
    build_fundamental_record,
    compute_metrics,
)
from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart


def test_parse_amount():
    assert _parse_amount("1,234") == 1234.0
    assert _parse_amount("(500)") == -500.0
    assert _parse_amount("-") is None


def test_compute_metrics_from_sample_rows():
    meta = ReportMeta(
        corp_code="00126380",
        bsns_year="2025",
        reprt_code="11011",
        rcept_no="20250220000123",
        rcept_dt="20250220",
        report_nm="사업보고서",
    )
    rows = [
        {"account_nm": "매출액", "sj_div": "IS", "thstrm_amount": "1000", "frmtrm_amount": "900"},
        {"account_nm": "영업이익", "sj_div": "IS", "thstrm_amount": "200", "frmtrm_amount": "180"},
        {"account_nm": "당기순이익", "sj_div": "IS", "thstrm_amount": "150", "frmtrm_amount": "100"},
        {"account_nm": "자산총계", "sj_div": "BS", "thstrm_amount": "5000"},
        {"account_nm": "부채총계", "sj_div": "BS", "thstrm_amount": "2000"},
        {"account_nm": "자본총계", "sj_div": "BS", "thstrm_amount": "3000"},
        {"account_nm": "매출총이익", "sj_div": "IS", "thstrm_amount": "400"},
        {"account_nm": "영업활동으로 인한 현금흐름", "sj_div": "CF", "thstrm_amount": "180"},
    ]
    metrics = compute_metrics(rows, meta)
    assert metrics["roe"] == pytest.approx(5.0, rel=0.01)
    assert metrics["operating_margin"] == pytest.approx(20.0, rel=0.01)
    assert metrics["earnings_yoy"] == pytest.approx(0.5, rel=0.01)


def test_report_meta_pit_dates():
    meta = ReportMeta(
        corp_code="00126380",
        bsns_year="2025",
        reprt_code="11013",
        rcept_no="20250515000123",
        rcept_dt="20250515",
        report_nm="1분기보고서",
    )
    assert meta.period_end == "2025-03-31"
    assert meta.report_date == "2025-05-15"
    assert meta.usable_from_date == "2025-05-16"


def test_build_fundamental_record_merges_valuation():
    meta = ReportMeta("c", "2025", "11011", "r", "20250220", "사업보고서")
    rec = build_fundamental_record(
        "005930",
        meta,
        {"roe": 10.0, "roa": 5.0},
        {"per": 12.0, "pbr": 1.2},
    )
    assert rec["per"] == 12.0
    assert rec["roe"] == 10.0
    assert rec["usable_from_date"] == "2025-02-21"


def test_enrich_fundamentals_mock(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "prices.csv").write_text(
        "date,ticker,close,market_cap,trading_value_20d,trading_value_60d,"
        "return_1m,return_3m,return_6m,return_12m,return_12m_ex_1m,"
        "high_52w,distance_from_52w_high,volatility_60d\n"
        "2026-06-17,005930,70000,400000000000000,10000000000,9000000000,"
        "0.01,0.02,0.03,0.04,0.03,72000,0.97,0.2\n",
        encoding="utf-8",
    )
    meta = ReportMeta("00126380", "2025", "11011", "r", "20250220", "사업보고서")
    rows = [
        {"account_nm": "매출액", "sj_div": "IS", "thstrm_amount": "1000"},
        {"account_nm": "영업이익", "sj_div": "IS", "thstrm_amount": "100"},
        {"account_nm": "당기순이익", "sj_div": "IS", "thstrm_amount": "80", "frmtrm_amount": "70"},
        {"account_nm": "자산총계", "sj_div": "BS", "thstrm_amount": "2000"},
        {"account_nm": "부채총계", "sj_div": "BS", "thstrm_amount": "800"},
        {"account_nm": "자본총계", "sj_div": "BS", "thstrm_amount": "1200"},
    ]

    with patch("src.data_refresh.dart_enrich.build_ticker_corp_map", return_value={"005930": "00126380"}), patch(
        "src.data_refresh.dart_enrich.find_latest_report", return_value=meta
    ), patch("src.data_refresh.dart_enrich.fetch_financial_accounts", return_value=rows):
        result = enrich_fundamentals_from_dart(data_dir, as_of="2026-06-17", tickers=["005930"])

    assert result.enriched == 1
    fund = data_dir / "fundamentals.csv"
    assert fund.exists()
    text = fund.read_text(encoding="utf-8")
    assert "005930" in text
    assert "usable_from_date" in text


def test_dart_api_key_missing(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    with pytest.raises(DartCredentialsError):
        get_dart_api_key()
