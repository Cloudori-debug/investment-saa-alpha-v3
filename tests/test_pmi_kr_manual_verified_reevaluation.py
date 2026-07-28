"""Tests for PMI KR manual_verified re-evaluation routine."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data_refresh.kosis_tier2_manual import validate_pmi_kr_manual_ready
from src.data_refresh.kosis_tier2_refresh import KosisTier2RefreshResult
from src.validation.pmi_kr_manual_verified_reevaluation import (
    build_pmi_kr_manual_verified_reevaluation,
    run_pmi_kr_manual_verified_reevaluation,
    write_pmi_kr_manual_verified_reevaluation,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_verified_false_skips_reevaluation(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "tier2_kosis_manual.yaml").write_text(
        "fields:\n  pmi_kr:\n    verified: false\n    value: null\n",
        encoding="utf-8",
    )
    val = validate_pmi_kr_manual_ready(data)
    assert val["ready"] is False
    doc = write_pmi_kr_manual_verified_reevaluation(data, out)
    assert doc["status"] == "manual_required_skipped"
    assert doc["actual_buy_trace"]["changed_from_zero"] is False
    assert doc["safety"]["pmi_alt_auto_map"] is False
    assert doc["safety"]["pmi_excluded_not_applied"] is True


def test_verified_true_requires_all_fields(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "tier2_kosis_manual.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  pmi_kr:",
                "    verified: true",
                "    value: 49.8",
                "    value_date: '2026-06-30'",
                "    source: manual:bank_of_korea",
                "    source_url_or_note: null",
                "    updated_by: operator",
                "    update_reason: test",
            ]
        ),
        encoding="utf-8",
    )
    val = validate_pmi_kr_manual_ready(data)
    assert val["verified"] is True
    assert val["ready"] is False
    assert "source_url_or_note" in val["missing_fields"]


def test_manual_verified_applies_provenance(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "tier2_kosis_manual.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  pmi_kr:",
                "    verified: true",
                "    value: 49.8",
                "    value_date: '2026-06-30'",
                "    source: manual:official_pmi",
                "    source_url_or_note: https://example.org/pmi",
                "    updated_by: operator",
                "    update_reason: verified official PMI source",
                "  cpi_kr_yoy:",
                "    verified: false",
            ]
        ),
        encoding="utf-8",
    )
    (data / "tier2_sources.yaml").write_text("kosis:\n  queries: {}\n", encoding="utf-8")
    (data / "macro_tier2.csv").write_text("date,cpi_kr_yoy,pmi_kr\n2026-07-06,3.2,51.2\n", encoding="utf-8")
    (data / "tier2_provenance.json").write_text(
        json.dumps(
            {
                "fields": {
                    "pmi_kr": {"status": "manual_required", "value": 51.2},
                    "cpi_kr_yoy": {"status": "fresh", "value": 3.2},
                }
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "final_execution_decision.json",
        "acceptance_report.json",
        "core_etf_permission_diagnostics.json",
        "policy_cap_counterfactual.json",
        "alpha_shortlist_summary.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    mock_result = KosisTier2RefreshResult(
        as_of="2026-07-06",
        refreshed_fields=["pmi_kr"],
        manual_applied_fields=["pmi_kr"],
        stale_after=[],
        manual_required_fields=[],
    )

    def _fake_refresh(data_dir: Path, **kwargs: object) -> KosisTier2RefreshResult:
        prov = {
            "as_of": "2026-07-06",
            "fields": {
                "pmi_kr": {
                    "field": "pmi_kr",
                    "status": "fresh",
                    "fetch_method": "manual_verified",
                    "fetch_status": "manual_verified",
                    "source": "manual:official_pmi",
                    "value_date": "2026-06-30",
                    "value": 49.8,
                },
                "cpi_kr_yoy": {"status": "fresh"},
            },
        }
        (data_dir / "tier2_provenance.json").write_text(json.dumps(prov), encoding="utf-8")
        return mock_result

    with patch(
        "src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics",
        side_effect=lambda d, o, **kw: (_fake_refresh(d), {}),
    ):
        with patch(
            "src.validation.core_etf_permission_diagnostics.write_core_etf_permission_diagnostics",
            return_value={},
        ):
            with patch(
                "src.validation.data_gate_diagnostics.write_data_gate_diagnostics",
                side_effect=lambda d, o: (
                    (o / "data_gate_diagnostics.json").write_text(
                        json.dumps(
                            {
                                "data_gate_status": "YELLOW",
                                "primary_data_blockers": [],
                                "secondary_data_blockers": ["pit_data_yellow"],
                                "stale_fields": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    or {}
                ),
            ):
                doc = run_pmi_kr_manual_verified_reevaluation(data, out)

    assert doc["status"] in {"manual_verified_applied", "manual_verified_pending_provenance"}
    assert doc["pmi_kr_provenance"]["manual_verified_recorded"] is True
    assert doc["checks"]["2_pmi_kr_removed_from_stale"] is True
    assert doc["checks"]["3_data_gate_primary_cleared"] is True
    assert doc["actual_buy_trace"]["final_actual_buy_allowed"] == 0


def test_live_skipped_when_not_verified() -> None:
    if not (DATA / "tier2_kosis_manual.yaml").exists():
        pytest.skip("manual yaml missing")
    doc = build_pmi_kr_manual_verified_reevaluation(DATA, OUT)
    assert doc["status"] == "manual_required_skipped"
    assert doc["validation"]["verified"] is False
