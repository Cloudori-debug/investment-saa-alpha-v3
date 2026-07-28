"""Tests for PMI KR source policy and data gate GREEN preflight."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.data_refresh.kosis_tier2_manual import load_verified_manual_overrides
from src.validation.data_gate_diagnostics import write_data_gate_diagnostics
from src.validation.data_gate_green_preflight import build_data_gate_green_preflight
from src.validation.pmi_kr_source_policy import build_pmi_kr_source_policy, write_pmi_kr_source_policy

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_pmi_kr_verified_false_keeps_manual_required() -> None:
    if not (DATA / "tier2_kosis_manual.yaml").exists():
        pytest.skip("manual yaml missing")
    doc = build_pmi_kr_source_policy(DATA, OUT)
    assert doc["manual_required"] is True
    assert doc["pmi_kr_status"] == "manual_required"
    assert doc["auto_map_alt_to_pmi_kr"] is False
    assert doc["manual_yaml_verified"] is False


def test_pmi_kr_alt_not_mapped_to_pmi_kr() -> None:
    if not (OUT / "kosis_tblid_discovery.json").exists():
        pytest.skip("discovery output missing")
    doc = build_pmi_kr_source_policy(DATA, OUT)
    for alt in doc.get("alternative_indicators") or []:
        assert alt.get("field") != "pmi_kr"
        assert alt.get("separate_field") == "pmi_kr_alt"
        assert "do not auto-map" in str(alt.get("recommended_mapping", "")).lower()


def test_no_verified_override_without_yaml(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "tier2_kosis_manual.yaml").write_text(
        "fields:\n  pmi_kr:\n    verified: false\n    value: null\n    value_date: null\n    source: null\n",
        encoding="utf-8",
    )
    (data / "tier2_provenance.json").write_text(
        json.dumps(
            {
                "fields": {
                    "pmi_kr": {"status": "manual_required", "source": "preserved", "value": 51.2},
                }
            }
        ),
        encoding="utf-8",
    )
    assert load_verified_manual_overrides(data) == {}
    doc = build_pmi_kr_source_policy(data, out)
    assert doc["manual_required"] is True


def test_preflight_outputs_and_current_matches(tmp_path: Path) -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    for name in (
        "tier2_provenance.json",
        "tier2_kosis_manual.yaml",
        "market_data_provenance.json",
        "market_indicators.csv",
    ):
        src = DATA / name
        if src.exists():
            shutil.copy(src, data / name)
    for name in (
        "final_execution_decision.json",
        "acceptance_report.json",
        "system_health.json",
        "decision_log.jsonl",
        "gpt_context.json",
        "price_coverage_report.json",
        "core_etf_permission_diagnostics.json",
        "policy_cap_counterfactual.json",
        "alpha_shortlist_summary.json",
        "kosis_tblid_discovery.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    write_data_gate_diagnostics(data, out)
    assert (out / "pmi_kr_source_policy.json").exists()
    assert (out / "data_gate_green_preflight.json").exists()

    pre = json.loads((out / "data_gate_green_preflight.json").read_text(encoding="utf-8"))
    dg = json.loads((out / "data_gate_diagnostics.json").read_text(encoding="utf-8"))
    current = pre["scenarios"]["current"]
    assert current["remaining_primary_blockers"] == dg["primary_data_blockers"]
    assert pre["summary"]["current_matches_actual"] is True


def test_counterfactual_does_not_change_actual_buy_allowed() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")
    pre = build_data_gate_green_preflight(DATA, OUT)
    actual = pre["actual_buy_allowed"]
    for scenario in pre["scenarios"].values():
        assert scenario["actual_buy_allowed_unchanged"] == actual
        assert "Counterfactual" in scenario["warning_counterfactual_only"]


def test_pmi_resolved_scenario_can_turn_green() -> None:
    if not (OUT / "data_gate_diagnostics.json").exists():
        pytest.skip("data gate diagnostics missing")
    pre = build_data_gate_green_preflight(DATA, OUT)
    resolved = pre["scenarios"]["pmi_kr_manual_verified_assumed"]
    alt = pre["scenarios"]["pmi_kr_alt_used_assumed"]
    if pre["summary"].get("pmi_only_primary_blocker"):
        assert resolved["would_data_gate_turn_green"] is True
        assert alt["would_data_gate_turn_green"] is False


def test_write_pmi_policy_json(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "tier2_kosis_manual.yaml").write_text("fields:\n  pmi_kr:\n    verified: false\n", encoding="utf-8")
    doc = write_pmi_kr_source_policy(data, out)
    assert (out / "pmi_kr_source_policy.json").exists()
    assert doc["warning"]
