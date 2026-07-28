"""Tests for KOSIS tier2 refresh and manual provenance."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data_refresh.kosis_tier2_manual import load_verified_manual_overrides
from src.data_refresh.kosis_tier2_refresh import refresh_kosis_tier2_fields
from src.validation.kosis_tier2_refresh_diagnostics import (
    run_kosis_tier2_refresh_with_diagnostics,
    write_kosis_tier2_refresh_diagnostics,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _kosis_fail(base_url, query, *, api_key):
    return None, "", f"KOSIS err=21: table missing (tbl={query.get('tblId')})"


def test_kosis_fail_soft_manual_required(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    shutil.copy(DATA_DIR / "macro_tier2.csv", data / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", data / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "tier2_provenance.json", data / "tier2_provenance.json")
    shutil.copy(DATA_DIR / "market_indicators.csv", data / "market_indicators.csv")
    shutil.copy(DATA_DIR / "tier2_kosis_manual.yaml.example", data / "tier2_kosis_manual.yaml")
    yaml_path = data / "tier2_sources.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").replace("DT_1J22042", "DT_1J20001"),
        encoding="utf-8",
    )

    with patch("src.data_refresh.kosis_tier2_refresh.fetch_kosis_field", side_effect=_kosis_fail):
        with patch("src.data_refresh.kosis_tier2_refresh._kosis_api_key", return_value="test-kosis"):
            result = refresh_kosis_tier2_fields(data, as_of="2026-07-06")

    assert result.failed_fields == ["cpi_kr_yoy", "pmi_kr"]
    assert result.manual_required_fields == ["cpi_kr_yoy", "pmi_kr"]
    assert not result.refreshed_fields
    prov = json.loads((data / "tier2_provenance.json").read_text(encoding="utf-8"))
    cpi = prov["fields"]["cpi_kr_yoy"]
    assert cpi["status"] == "manual_required"
    assert cpi["fetch_status"] == "failed"
    assert cpi["value"] is not None
    assert "manual provenance" in cpi.get("recommended_fix", "")


def test_manual_verified_applies_without_kosis(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    shutil.copy(DATA_DIR / "macro_tier2.csv", data / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", data / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "tier2_provenance.json", data / "tier2_provenance.json")
    shutil.copy(DATA_DIR / "market_indicators.csv", data / "market_indicators.csv")
    (data / "tier2_kosis_manual.yaml").write_text(
        """
fields:
  cpi_kr_yoy:
    verified: true
    value: 2.1
    value_date: "2026-05-01"
    source: "manual:statistics_korea_press_release"
    source_url_or_note: "https://kostat.go.kr/example"
    updated_by: "test"
    update_reason: "verified official release"
  pmi_kr:
    verified: false
""",
        encoding="utf-8",
    )

    with patch("src.data_refresh.kosis_tier2_refresh.fetch_kosis_field", side_effect=_kosis_fail):
        with patch("src.data_refresh.kosis_tier2_refresh._kosis_api_key", return_value="test-kosis"):
            result = refresh_kosis_tier2_fields(data, as_of="2026-07-06")

    assert "cpi_kr_yoy" in result.manual_applied_fields
    assert "cpi_kr_yoy" in result.refreshed_fields
    assert "pmi_kr" in result.manual_required_fields
    prov = json.loads((data / "tier2_provenance.json").read_text(encoding="utf-8"))
    cpi = prov["fields"]["cpi_kr_yoy"]
    assert cpi["fetch_method"] == "manual_verified"
    assert cpi["status"] == "fresh"
    assert int(cpi["stale_days"]) <= 60
    assert load_verified_manual_overrides(data)["cpi_kr_yoy"]["value"] == 2.1


def test_kosis_diagnostics_json_written(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    shutil.copy(DATA_DIR / "macro_tier2.csv", data / "macro_tier2.csv")
    shutil.copy(DATA_DIR / "tier2_sources.yaml", data / "tier2_sources.yaml")
    shutil.copy(DATA_DIR / "tier2_provenance.json", data / "tier2_provenance.json")
    shutil.copy(DATA_DIR / "market_indicators.csv", data / "market_indicators.csv")
    shutil.copy(DATA_DIR / "tier2_kosis_manual.yaml.example", data / "tier2_kosis_manual.yaml")

    with patch("src.data_refresh.kosis_tier2_refresh.fetch_kosis_field", side_effect=_kosis_fail):
        with patch("src.data_refresh.kosis_tier2_refresh._kosis_api_key", return_value="test-kosis"):
            _result, doc = run_kosis_tier2_refresh_with_diagnostics(data, out, as_of="2026-07-06")

    assert (out / "kosis_tier2_refresh_diagnostics.json").exists()
    assert doc["manual_required_fields"] == ["cpi_kr_yoy", "pmi_kr"]
    assert doc["kosis_fetch_errors"]
    assert "manual provenance" in doc["recommended_next_action"][0]


def test_kosis_diagnostics_from_live_outputs() -> None:
    out = DATA_DIR.parent / "outputs"
    if not (out / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")
    path = out / "kosis_tier2_refresh_diagnostics.json"
    if not path.exists():
        pytest.skip("kosis diagnostics not generated yet")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["target_fields"] == ["cpi_kr_yoy", "pmi_kr"]
