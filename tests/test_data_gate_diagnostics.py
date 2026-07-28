"""Tests for data_gate diagnostics."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from src.validation.alpha_gate_diagnostics import build_alpha_gate_diagnostics
from src.validation.core_etf_permission_diagnostics import build_core_etf_permission_diagnostics
from src.validation.data_gate_diagnostics import (
    build_data_gate_diagnostics,
    write_data_gate_diagnostics,
)
from src.validation.no_action_diagnostics import write_no_action_diagnostics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_data_gate_diagnostics_from_outputs() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_data_gate_diagnostics(DATA, OUT)
    assert doc["data_gate_status"] == "YELLOW"
    assert doc["primary_data_blockers"] or doc["secondary_data_blockers"]
    assert doc["stale_fields"]
    assert "pmi_kr" in doc["stale_fields"]
    assert "cpi_kr_yoy" not in doc["stale_fields"]
    mixed = doc.get("mixed_market_fields") or []
    for name in ("sp500", "vix", "usdkrw"):
        assert name not in mixed
    assert (doc["sector_data_status"] or {}).get("resolved") is True
    assert doc["impact_on_core_etf_permission"]["aligned_with_core_etf_diagnostics"]
    assert doc["impact_on_alpha_gate"]["aligned_with_alpha_gate_diagnostics"]
    assert doc["impact_on_actual_buy_allowed"]["actual_buy_allowed"] == 0


def test_data_gate_field_csv_and_trace() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for name in (
            "final_execution_decision.json",
            "acceptance_report.json",
            "decision_log.jsonl",
            "system_health.json",
            "gpt_context.json",
            "price_coverage_report.json",
            "core_etf_permission_diagnostics.json",
            "policy_cap_counterfactual.json",
            "alpha_shortlist_summary.json",
        ):
            src = OUT / name
            if src.exists():
                shutil.copy(src, out / name)

        doc = write_data_gate_diagnostics(DATA, out)
        assert (out / "data_gate_diagnostics.json").exists()
        assert (out / "data_gate_field_status.csv").exists()
        assert (out / "data_gate_to_permission_trace.json").exists()

        with (out / "data_gate_field_status.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        field_names = {r["field_name"] for r in rows}
        assert "cpi_kr_yoy" in field_names
        assert "pmi_kr" in field_names
        mixed = [r for r in rows if r.get("fail_reason") == "market_field_mixed"]
        market_mixed_names = {r["field_name"] for r in mixed}
        for name in ("sp500", "vix", "usdkrw"):
            assert name not in market_mixed_names

        trace = json.loads((out / "data_gate_to_permission_trace.json").read_text(encoding="utf-8"))
        assert trace["data_gate_status"] == doc["data_gate_status"]
        assert trace["etf_path_blocked_by_data_gate"] is True
        assert trace["alpha_path_separate_blocker"] == "shortlist_eligible=0"
        assert trace["counterfactual_data_gate_green"]["would_open_buy_path"] is True


def test_core_etf_and_alpha_alignment() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    dg = build_data_gate_diagnostics(DATA, OUT)
    core = build_core_etf_permission_diagnostics(DATA, OUT)
    alpha = build_alpha_gate_diagnostics(DATA, OUT)

    assert dg["data_gate_status"] == core["data_gate_status"]
    assert dg["alpha_gate_status"] == alpha["alpha_gate_status"]
    assert dg["impact_on_core_etf_permission"]["core_etf_permission"] == core["core_etf_permission"]


def test_no_action_includes_data_gate_path(tmp_path: Path) -> None:
    from tests.test_no_action_diagnostics import _fixture

    data, out = _fixture(tmp_path)
    doc = write_no_action_diagnostics(data, out)
    assert doc.get("data_gate_diagnostics_path") == "outputs/data_gate_diagnostics.json"
    assert "data_gate_status" in (doc.get("data_gate_diagnostic") or {})
    assert any("data_gate=" in s for s in doc.get("secondary_blockers") or [])


def test_etf_only_not_buy_permission_in_trace(tmp_path: Path) -> None:
    from tests.test_no_action_diagnostics import _fixture

    data, out = _fixture(tmp_path)
    write_data_gate_diagnostics(data, out)
    trace = json.loads((out / "data_gate_to_permission_trace.json").read_text(encoding="utf-8"))
    assert "not ETF buy permission" in trace.get("execution_scope_note", "")
