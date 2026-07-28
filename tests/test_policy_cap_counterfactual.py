"""Tests for policy cap counterfactual analysis."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.validation.no_action_diagnostics import build_no_action_diagnostics, write_no_action_diagnostics
from src.validation.policy_cap_counterfactual import (
    build_policy_cap_counterfactual,
    write_policy_cap_counterfactual,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_policy_cap_counterfactual_from_outputs() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_policy_cap_counterfactual(DATA, OUT)
    scenarios = doc["scenarios"]
    assert "policy_cap" in doc
    assert "active" in doc["policy_cap"]
    assert "cap_regime" in doc["policy_cap"]
    assert "current_policy" in scenarios
    assert "policy_cap_removed_only" in scenarios
    assert "all_soft_blockers_cleared" in scenarios

    removed = scenarios["policy_cap_removed_only"]
    assert removed["hypothetical_actual_buy_allowed"] == 0 or isinstance(
        removed["hypothetical_actual_buy_allowed"], int
    )
    assert removed["would_open_buy_path"] is False
    assert removed["shortlist_eligible_count"] == doc["actual_state"]["shortlist_eligible_count"]


def test_policy_cap_removed_does_not_change_config(tmp_path: Path) -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "outputs"
    data_dir.mkdir()
    out_dir.mkdir()
    shutil.copytree(DATA, data_dir, dirs_exist_ok=True)
    for name in (
        "final_execution_decision.json",
        "acceptance_report.json",
        "gpt_context.json",
        "alpha_shortlist_summary.json",
        "system_health.json",
        "shadow_diagnostic.json",
        "decision_log.jsonl",
        "daily_brief.json",
        "alpha_v2_summary.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out_dir / name)

    before = json.loads((out_dir / "final_execution_decision.json").read_text(encoding="utf-8"))
    cap_before = before.get("policy_cap", {}).get("active")

    write_policy_cap_counterfactual(data_dir, out_dir)
    after = json.loads((out_dir / "final_execution_decision.json").read_text(encoding="utf-8"))
    assert after.get("policy_cap", {}).get("active") == cap_before
    assert (out_dir / "policy_cap_counterfactual.json").exists()


def test_shortlist_zero_blocks_alpha_path(tmp_path: Path) -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "outputs"
    data_dir.mkdir()
    out_dir.mkdir()
    shutil.copytree(DATA, data_dir, dirs_exist_ok=True)
    for name in (
        "final_execution_decision.json",
        "acceptance_report.json",
        "gpt_context.json",
        "system_health.json",
        "shadow_diagnostic.json",
        "alpha_shortlist_summary.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out_dir / name)

    summary = json.loads((out_dir / "alpha_shortlist_summary.json").read_text(encoding="utf-8"))
    summary["shortlist_eligible_count"] = 0
    (out_dir / "alpha_shortlist_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    doc = build_policy_cap_counterfactual(data_dir, out_dir)
    green = doc["scenarios"]["policy_cap_removed_and_alpha_gate_green"]
    assert green["would_open_buy_path"] is False
    assert "shortlist_eligible=0" in ";".join(green["remaining_blockers"])


def test_no_action_includes_counterfactual_scenarios(tmp_path: Path) -> None:
    from tests.test_no_action_diagnostics import _fixture

    data, out = _fixture(tmp_path)
    (out / "alpha_shortlist_summary.json").write_text(
        json.dumps({"shortlist_eligible_count": 0, "b_grade_count": 0}),
        encoding="utf-8",
    )
    doc = write_no_action_diagnostics(data, out)
    cf = doc["counterfactual_results"]
    assert cf.get("disclaimer")
    assert "policy_cap_removed_only" in cf
    assert doc.get("policy_cap_counterfactual_path") == "outputs/policy_cap_counterfactual.json"


def test_core_etf_unrestricted_may_open_etf_path() -> None:
    if not (OUT / "final_execution_decision.json").exists():
        pytest.skip("outputs not present")

    doc = build_policy_cap_counterfactual(DATA, OUT)
    etf = doc["scenarios"]["policy_cap_removed_and_core_etf_unrestricted"]
    assert etf["eligible_etf_candidates_count"] >= 0
    if etf["eligible_etf_candidates_count"] > 0:
        assert etf["core_etf_permission"] == "ALLOWED"
        assert etf["would_open_buy_path"] is True
        assert etf["hypothetical_actual_buy_allowed"] > 0
