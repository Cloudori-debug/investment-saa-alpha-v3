"""Tests for core ETF permission diagnostics."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from src.validation.core_etf_permission_diagnostics import (
    build_core_etf_permission_diagnostics,
    list_etf_underweight_candidates,
    write_core_etf_permission_diagnostics,
)
from src.validation.no_action_diagnostics import write_no_action_diagnostics
from src.validation.policy_cap_counterfactual import build_policy_cap_counterfactual

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_core_etf_diagnostics_from_outputs() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_core_etf_permission_diagnostics(DATA, OUT)
    assert doc["core_etf_permission"] in {"ALLOWED", "RESTRICTED", "BLOCKED"}
    assert doc["eligible_etf_underweight_count"] == 11
    assert doc["hypothetical_etf_buy_count_if_unrestricted"] == 11
    assert doc["actual_buy_allowed"] == 0
    assert "data_gate" in ";".join(doc["restriction_reasons"]).lower() or doc["data_gate_status"]


def test_etf_trace_csv_matches_counterfactual() -> None:
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
            "shadow_diagnostic.json",
            "current_vs_target.csv",
            "policy_cap_counterfactual.json",
        ):
            src = OUT / name
            if src.exists():
                shutil.copy(src, out / name)

        doc = write_core_etf_permission_diagnostics(DATA, out)
        assert (out / "core_etf_candidate_trace.csv").exists()
        with (out / "core_etf_candidate_trace.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == doc["eligible_etf_underweight_count"]
        assert sum(1 for r in rows if r["candidate_if_unrestricted"] == "True") == 11
        assert all(r["actual_buy_permission"] == "False" for r in rows)


def test_etf_only_not_buy_permission_in_doc() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_core_etf_permission_diagnostics(DATA, OUT)
    assert "not ETF buy permission" in doc["execution_scope_note"]


def test_no_action_includes_core_etf_path(tmp_path: Path) -> None:
    from tests.test_no_action_diagnostics import _fixture

    data, out = _fixture(tmp_path)
    (out / "current_vs_target.csv").write_text(
        "ticker,name,asset_group,current_weight,target_weight,gap,status\n"
        "360750,TIGER 미국S&P500,global_beta,0.24,12.66,12.42,Underweight\n",
        encoding="utf-8",
    )
    final = json.loads((out / "final_execution_decision.json").read_text(encoding="utf-8"))
    final["allowed_actions"] = [{
        "ticker": "360750", "name": "TIGER 미국S&P500", "action": "Wait",
        "allowed_size_pct": 0.0, "reason": "Underweight but stop-buy or data caution", "priority": "High",
    }]
    (out / "final_execution_decision.json").write_text(json.dumps(final), encoding="utf-8")

    doc = write_no_action_diagnostics(data, out)
    assert doc.get("core_etf_diagnostics_path") == "outputs/core_etf_permission_diagnostics.json"
    assert "core_etf_permission" in (doc.get("core_etf_permission_diagnostic") or {})


def test_policy_cap_etf_scenario_clarity_fields() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_policy_cap_counterfactual(DATA, OUT)
    etf = doc["scenarios"]["policy_cap_removed_and_core_etf_unrestricted"]
    assert etf.get("first_remaining_blocker_for_etf_path") == "none_for_etf_path"
    assert etf.get("residual_scope_constraint") == "ETF_ONLY"
    assert etf.get("alpha_path_blocker") == "shortlist_eligible=0"
