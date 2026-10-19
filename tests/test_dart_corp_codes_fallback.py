"""corpCode download failure must not erase a usable local cache."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data_refresh import dart_corp_codes as mod


def test_stale_cache_used_when_download_not_zip(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache" / "dart_corp_codes.csv"
    cache.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "modify_date": "20200101",
            }
        ]
    ).to_csv(cache, index=False, encoding="utf-8-sig")
    # Force "expired" path then bad payload.
    monkeypatch.setattr(
        mod,
        "dart_get_bytes",
        lambda *a, **k: b"<!DOCTYPE html>not a zip",
    )
    # Pretend cache is old by temporarily lowering max_age to 0 via call.
    # Age check: file is new — force download by patching timedelta path:
    # call with max_age_days=-1 so age always exceeds.
    table = mod.download_corp_code_table(tmp_path, max_age_days=-1)
    assert len(table) == 1
    assert table.iloc[0]["stock_code"] == "005930"
    mapped = mod.build_ticker_corp_map(tmp_path, ["005930", "000660"])
    assert mapped["005930"] == "00126380"


def test_fresh_cache_skips_network(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache" / "dart_corp_codes.csv"
    cache.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "modify_date": "20200101",
            }
        ]
    ).to_csv(cache, index=False, encoding="utf-8-sig")

    def boom(*_a, **_k):
        raise AssertionError("network should not run")

    monkeypatch.setattr(mod, "dart_get_bytes", boom)
    table = mod.download_corp_code_table(tmp_path, max_age_days=30)
    assert len(table) == 1
