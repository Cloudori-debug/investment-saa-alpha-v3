"""DART quota + evidence cache — no network."""

from __future__ import annotations

from pathlib import Path

from alpha_system.shadow.evidence_ab import evidence_ab_report
from alpha_system.ui.services.dart_evidence_cache import (
    extract_amount_from_document_text,
    extract_div_amount_from_document_text,
    is_fresh,
    load_ticker_cache,
    merge_amounts,
    save_ticker_cache,
)
from alpha_system.ui.services.dart_quota import load_quota, save_quota


def test_quota_rolls_daily(tmp_path: Path) -> None:
    q = load_quota(tmp_path, soft_limit=100)
    assert q.can_call(10)
    q.record("list.json", 5)
    save_quota(tmp_path, q)
    q2 = load_quota(tmp_path, soft_limit=100)
    assert q2.calls == 5
    assert q2.remaining() == 95


def test_ticker_cache_roundtrip(tmp_path: Path) -> None:
    save_ticker_cache(
        tmp_path,
        "005930",
        {"payout_events": [{"kind": "buyback", "rcept_no": "1"}], "as_of": "2026-10-18"},
    )
    raw = load_ticker_cache(tmp_path, "005930")
    assert raw is not None
    assert is_fresh(str(raw.get("fetched_at") or ""))
    assert raw["payout_events"][0]["kind"] == "buyback"


def test_merge_amounts_and_doc_parse(tmp_path: Path) -> None:
    merge_amounts(tmp_path, {"20260515000001": (1_000_000_000, "tsstkAqDecsn")})
    from alpha_system.ui.services.dart_evidence_cache import amounts_as_tuples, load_amounts

    assert amounts_as_tuples(load_amounts(tmp_path))["20260515000001"][0] == 1_000_000_000
    amt, note = extract_amount_from_document_text("취득예정금액 50억원 이내")
    assert amt == 5_000_000_000
    assert "억" in note


def test_extract_div_total_and_dps() -> None:
    total_blob = (
        "배당구분 결산배당 배당종류 현금배당 "
        "1주당 배당금(원) 보통주 361 기타주식 - "
        "시가배당율(%) 보통주 1.2 "
        "배당금총액(원) 12,345,678,901"
    )
    amt, note = extract_div_amount_from_document_text(total_blob)
    assert amt == 12_345_678_901
    assert "배당금총액" in note

    dps_only = "1주당 배당금(원) 보통주 1,446 시가배당율 2.1"
    amt2, note2 = extract_div_amount_from_document_text(dps_only)
    assert amt2 == 1446
    assert "1주당" in note2

    # Via generic extractor
    amt3, note3 = extract_amount_from_document_text(total_blob)
    assert amt3 == 12_345_678_901
    assert "배당금총액" in note3


def test_evidence_ab_offline() -> None:
    rep = evidence_ab_report(
        ["005930", "000660", "005380"],
        ["000660"],
        score_by_ticker={"005930": 70.0, "000660": 40.0, "005380": 60.0},
    )
    assert rep["dart_calls"] == 0
    assert rep["n_a"] == 3
    assert rep["n_b"] == 2
    assert rep["removed"] == ["000660"]
    assert rep["writes_target"] is False
