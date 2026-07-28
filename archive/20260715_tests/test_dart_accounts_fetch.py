from __future__ import annotations

from unittest.mock import patch

import pytest

from src.data_refresh.dart_accounts_fetch import (
    AccountsFetchAttempt,
    AccountsFetchResult,
    FAILURE_ACTIONS,
    PHASE4E_FAILURE_CATEGORIES,
    classify_fetch_failure,
    validate_corp_code,
)


def test_validate_corp_code() -> None:
    assert validate_corp_code("00126380")[0] is True
    assert validate_corp_code("123")[0] is False
    assert validate_corp_code(None)[1] == "corp_code_mapping_error"


def test_classify_fetch_failure_status_013() -> None:
    attempts = [
        AccountsFetchAttempt("00126380", "2025", "11011", "CFS", "013", "no data", 0),
        AccountsFetchAttempt("00126380", "2025", "11011", "OFS", "013", "no data", 0),
    ]
    cat, _ = classify_fetch_failure(attempts)
    assert cat == "accounts_api_empty_status_013"


def test_classify_fetch_failure_rate_limit() -> None:
    attempts = [
        AccountsFetchAttempt("00126380", "2025", "11011", "CFS", "020", "limit", 0, error="020"),
    ]
    cat, _ = classify_fetch_failure(attempts)
    assert cat == "request_limit_or_api_error"


def test_failure_actions_cover_categories() -> None:
    for cat in PHASE4E_FAILURE_CATEGORIES:
        if cat in ("no_report", "no_corp_code"):
            continue
        assert cat in FAILURE_ACTIONS or cat.startswith("accounts_")


def test_fetch_fallback_success_mock() -> None:
    from src.data_refresh.dart_accounts_fetch import fetch_financial_accounts_with_fallback

    rows = [{"account_nm": "영업활동현금흐름", "sj_div": "CF", "thstrm_amount": "100"}]

    def fake_raw(corp, year, code, fs, *, limiter=None):
        if fs == "OFS" and code == "11014":
            return AccountsFetchAttempt(corp, year, code, fs, "000", "ok", 1, rows=rows)
        return AccountsFetchAttempt(corp, year, code, fs, "013", "empty", 0)

    with patch("src.data_refresh.dart_accounts_fetch.fetch_accounts_raw", side_effect=fake_raw):
        result = fetch_financial_accounts_with_fallback("00126380", "2026-06-28", years=["2025"])
    assert result.success is True
    assert len(result.accounts) == 1


def test_debug_writes_without_dart(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.value_list.dart_accounts_debug import run_dart_accounts_debug

    monkeypatch.setattr(
        "src.settings.user_secrets.credential_status",
        lambda _d: {"dart": False},
    )
    report = run_dart_accounts_debug(tmp_path, tmp_path / "out", as_of="2026-06-28")
    assert report.get("error") == "request_limit_or_api_error"
    assert (tmp_path / "out" / "dart_accounts_debug_summary.json").exists()
