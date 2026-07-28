"""Tests for market indicator schema normalization."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.data_provenance import audit_market_data_consistency
from src.validation.data_gate_diagnostics import build_data_gate_diagnostics
from src.validation.market_indicator_schema import (
    load_normalized_provenance,
    market_mixed_blocker_fields,
    normalize_field_meta,
    normalize_provenance_doc,
    reconcile_market_provenance_schema,
)
from src.validation.market_indicator_schema_diagnostics import (
    build_market_indicator_schema_diagnostics,
    write_market_indicator_schema_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_legacy_last_updated_migrates_to_value_date() -> None:
    meta = {
        "source": "yahoo_chart",
        "last_updated": "2026-07-02",
        "stale_business_days": 1,
        "value": 7483.24,
    }
    norm, mixed, _ = normalize_field_meta("sp500", meta, as_of="2026-07-03", prov_updated_at="2026-07-06T08:00:00")
    assert norm["value_date"] == "2026-07-02"
    assert mixed is False
    assert norm["mixed_schema_flag"] is False


def test_calendar_lag_not_schema_mixed() -> None:
    prov = {
        "as_of": "2026-07-03",
        "updated_at": "2026-07-06T08:10:54",
        "fields": {
            "sp500": {"source": "yahoo_chart", "last_updated": "2026-07-02", "value": 7483.24, "stale_business_days": 1},
            "vix": {"source": "yahoo_chart", "last_updated": "2026-07-02", "value": 16.15, "stale_business_days": 1},
            "usdkrw": {"source": "unknown", "last_updated": "2026-07-03", "value": 1528.38, "stale_business_days": 0},
        },
    }
    normalized = normalize_provenance_doc(prov, as_of="2026-07-03")
    mixed = market_mixed_blocker_fields(normalized["fields"])
    assert mixed == []
    value_dates = {k: v["value_date"] for k, v in normalized["fields"].items()}
    assert len(set(value_dates.values())) > 1


def test_reconcile_live_provenance() -> None:
    if not (DATA / "market_data_provenance.json").exists():
        pytest.skip("provenance missing")
    reconcile_market_provenance_schema(DATA)
    normalized = load_normalized_provenance(DATA)
    assert normalized is not None
    assert normalized.get("schema_version") == "2.0"
    for name in ("sp500", "vix", "usdkrw"):
        if name in normalized.get("fields", {}):
            assert normalized["fields"][name].get("value_date")
            assert normalized["fields"][name].get("mixed_schema_flag") is False


def test_market_schema_diagnostics_clears_mixed_blocker() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")
    doc = build_market_indicator_schema_diagnostics(DATA, OUT)
    assert doc["market_schema_status"] in {"NORMALIZED", "STALE"}
    for name in ("sp500", "vix", "usdkrw"):
        if name in doc.get("field_value_dates", {}):
            assert name not in doc.get("mixed_fields", [])


def test_data_gate_no_market_field_mixed_for_sp500_vix_usdkrw() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    reconcile_market_provenance_schema(DATA)
    doc = build_data_gate_diagnostics(DATA, OUT)
    mixed = doc.get("mixed_market_fields") or []
    for name in ("sp500", "vix", "usdkrw"):
        assert name not in mixed
    assert "market_field_mixed" not in (doc.get("primary_data_blockers") or [])


def test_schema_diagnostics_outputs(tmp_path: Path) -> None:
    if not (DATA / "market_data_provenance.json").exists():
        pytest.skip("provenance missing")
    out = tmp_path / "outputs"
    write_market_indicator_schema_diagnostics(DATA, out)
    assert (out / "market_indicator_schema_diagnostics.json").exists()
    assert (out / "market_field_status.csv").exists()
    with (out / "market_field_status.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    sp500_rows = [r for r in rows if r["field"] == "sp500"]
    if sp500_rows:
        assert sp500_rows[0]["mixed_schema_flag"] in {"False", "false", ""}


def test_audit_no_legacy_mixed_issue() -> None:
    if not (DATA / "market_data_provenance.json").exists():
        pytest.skip("provenance missing")
    reconcile_market_provenance_schema(DATA)
    audit = audit_market_data_consistency(DATA)
    issues = audit.get("issues") or []
    assert not any("혼재" in str(i) for i in issues)
    assert not audit.get("schema_mixed_fields")
