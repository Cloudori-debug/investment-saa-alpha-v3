"""Tests for tier2 refresh diagnostics and monthly stale reference."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data_refresh.tier2_refresh import (
    _month_end_date,
    _stale_reference_date,
    reconcile_tier2_provenance_staleness,
    refresh_macro_tier2,
)
from src.validation.tier2_refresh_diagnostics import (
    build_tier2_refresh_diagnostics,
    write_tier2_refresh_diagnostics,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _fred_mock(base_url, *, series_id, api_key, transform):
    mapping = {
        "CPIAUCSL": (2.8, "2026-05-01", None),
        "T10Y2Y": (0.42, "2026-07-02", None),
        "BAMLH0A0HYM2": (3.85, "2026-07-02", None),
        "UMCSENT": (65.5, "2026-05-01", None),
    }
    if not api_key:
        return None, "", "FRED_API_KEY 미설정"
    val, dt, err = mapping.get(series_id, (None, "", "unknown"))
    if series_id == "BAMLH0A0HYM2" and val is not None:
        val = round(val * 100, 1)
    return val, dt, err


def _kosis_mock(base_url, query, *, api_key):
    return None, "", "empty"


def test_month_end_stale_reference() -> None:
    assert _month_end_date("2026-05-01") == "2026-05-31"
    assert _stale_reference_date("2026-05-01", "monthly") == "2026-05-31"
    assert _stale_reference_date("2026-07-02", "daily") == "2026-07-02"


def test_monthly_fields_fresh_after_refresh(tmp_path: Path) -> None:
    shutil.copy(DATA_DIR / "macro_tier2.csv", tmp_path / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", tmp_path / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "market_indicators.csv", tmp_path / "market_indicators.csv")
    if (DATA_DIR / "tier2_provenance.json").exists():
        shutil.copy(DATA_DIR / "tier2_provenance.json", tmp_path / "tier2_provenance.json")

    with patch("src.data_refresh.tier2_refresh.fetch_fred_field", side_effect=_fred_mock):
        with patch("src.data_refresh.tier2_refresh.fetch_kosis_field", side_effect=_kosis_mock):
            with patch("src.data_refresh.tier2_refresh._fred_api_key", return_value="test-fred"):
                with patch("src.data_refresh.tier2_refresh._kosis_api_key", return_value="test-kosis"):
                    result = refresh_macro_tier2(tmp_path, as_of="2026-07-06")

    prov = json.loads((tmp_path / "tier2_provenance.json").read_text(encoding="utf-8"))
    cpi = prov["fields"]["cpi_us_yoy"]
    pmi = prov["fields"]["pmi_us"]
    assert cpi["status"] == "fresh"
    assert pmi["status"] == "fresh"
    assert int(cpi["stale_business_days"]) <= 45
    assert int(pmi["stale_business_days"]) <= 45
    assert cpi["stale_reference_date"] == "2026-05-31"
    assert "cpi_us_yoy" not in result.stale_after
    assert "pmi_us" not in result.stale_after


def test_tier2_refresh_diagnostics_written(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "outputs"
    data_dir.mkdir()
    out_dir.mkdir()
    shutil.copy(DATA_DIR / "macro_tier2.csv", data_dir / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", data_dir / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "market_indicators.csv", data_dir / "market_indicators.csv")

    with patch("src.data_refresh.tier2_refresh.fetch_fred_field", side_effect=_fred_mock):
        with patch("src.data_refresh.tier2_refresh.fetch_kosis_field", side_effect=_kosis_mock):
            with patch("src.data_refresh.tier2_refresh._fred_api_key", return_value="test-fred"):
                with patch("src.data_refresh.tier2_refresh._kosis_api_key", return_value="test-kosis"):
                    result = refresh_macro_tier2(data_dir, as_of="2026-07-06")

    doc = write_tier2_refresh_diagnostics(
        refresh_result=result,
        data_dir=data_dir,
        output_dir=out_dir,
        stale_before=["cpi_us_yoy", "pmi_us"],
    )
    assert (out_dir / "tier2_refresh_diagnostics.json").exists()
    assert "cpi_us_yoy" not in doc["stale_after"]
    assert doc["alpha_gate_expected_impact"] == "tier2_stale_cleared_expected_alpha_gate_relief"


def test_reconcile_without_api_fetch(tmp_path: Path) -> None:
    shutil.copy(DATA_DIR / "tier2_sources.yaml", tmp_path / "tier2_sources.yaml")
    stale_prov = {
        "as_of": "2026-07-06",
        "fields": {
            "cpi_us_yoy": {
                "source": "fred:CPIAUCSL",
                "last_updated": "2026-05-01",
                "value_date": "2026-05-01",
                "value": 2.8,
                "stale_business_days": 46,
                "fallback_used": False,
            },
        },
    }
    (tmp_path / "tier2_provenance.json").write_text(
        json.dumps(stale_prov, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    reconcile_tier2_provenance_staleness(tmp_path, as_of="2026-07-06")
    prov = json.loads((tmp_path / "tier2_provenance.json").read_text(encoding="utf-8"))
    cpi = prov["fields"]["cpi_us_yoy"]
    assert cpi["status"] == "fresh"
    assert int(cpi["stale_business_days"]) <= 45
