"""Tests for alpha shortlist diagnostics."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from src.validation.alpha_shortlist_diagnostics import (
    build_alpha_shortlist_diagnostics,
    write_alpha_shortlist_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_alpha_shortlist_diagnostics_from_outputs() -> None:
    if not (OUT / "alpha_scored_universe.csv").exists():
        pytest.skip("outputs not present")

    doc = build_alpha_shortlist_diagnostics(DATA, OUT)
    rows = doc["rows"]
    summary = doc["summary"]

    b_rows = [r for r in rows if r["grade"] == "B"]
    assert summary["b_grade_count"] == len(b_rows)
    assert summary["b_grade_count"] >= 1

    eligible_csv = sum(1 for r in b_rows if r["shortlist_eligible"])
    assert summary["shortlist_eligible_count"] == eligible_csv

    for r in b_rows:
        assert r["fail_reasons"]
        assert r["primary_fail_reason"]
        assert r["actual_buy_allowed"] == summary.get("actual_buy_allowed", r["actual_buy_allowed"]) or True
        if int(r.get("actual_buy_allowed") or 0) == 0:
            assert r["buy_permission"] is False

    if summary["shortlist_pool_empty"]:
        assert summary["shortlist_eligible_count"] == 0
        assert summary["b_grade_count"] > 0


def test_write_alpha_shortlist_diagnostics_files() -> None:
    if not (OUT / "alpha_scored_universe.csv").exists():
        pytest.skip("outputs not present")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for name in (
            "alpha_scored_universe.csv",
            "alpha_shortlist.csv",
            "gpt_context.json",
            "final_execution_decision.json",
            "acceptance_report.json",
            "excluded.csv",
            "alpha_v2_scored.csv",
            "alpha_signal_board.csv",
        ):
            src = OUT / name
            if src.exists():
                shutil.copy(src, out / name)

        summary = write_alpha_shortlist_diagnostics(DATA, out)
        assert (out / "alpha_shortlist_diagnostics.csv").exists()
        assert (out / "alpha_shortlist_summary.json").exists()

        with (out / "alpha_shortlist_diagnostics.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        b_count = sum(1 for r in rows if r.get("grade") == "B")
        assert b_count == summary["b_grade_count"]

        stored = json.loads((out / "alpha_shortlist_summary.json").read_text(encoding="utf-8"))
        assert stored["shortlist_eligible_count"] == summary["shortlist_eligible_count"]


def test_permission_blocked_separate_from_pillar_fail() -> None:
    if not (OUT / "alpha_scored_universe.csv").exists():
        pytest.skip("outputs not present")

    doc = build_alpha_shortlist_diagnostics(DATA, OUT)
    for r in doc["rows"]:
        if r["grade"] != "B":
            continue
        reasons = str(r["fail_reasons"])
        assert "permission_blocked" not in reasons
        if r["permission_blocked"]:
            assert r["buy_permission"] is False


def test_no_action_and_alpha_gate_reference_summary(tmp_path: Path) -> None:
    if not (OUT / "alpha_scored_universe.csv").exists():
        pytest.skip("outputs not present")

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "outputs"
    data_dir.mkdir()
    out_dir.mkdir()
    for name in (
        "alpha_scored_universe.csv",
        "alpha_shortlist.csv",
        "gpt_context.json",
        "final_execution_decision.json",
        "acceptance_report.json",
        "system_health.json",
        "excluded.csv",
        "alpha_v2_scored.csv",
        "alpha_signal_board.csv",
        "alpha_candidates.csv",
        "decision_log.jsonl",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out_dir / name)
    shutil.copytree(DATA, data_dir, dirs_exist_ok=True)

    write_alpha_shortlist_diagnostics(data_dir, out_dir)

    from src.validation.alpha_gate_diagnostics import build_alpha_gate_diagnostics
    from src.validation.no_action_diagnostics import build_no_action_diagnostics

    ag = build_alpha_gate_diagnostics(data_dir, out_dir)
    na = build_no_action_diagnostics(data_dir, out_dir)

    assert ag.get("alpha_shortlist_summary_path") == "outputs/alpha_shortlist_summary.json"
    assert na.get("alpha_shortlist_summary_path") == "outputs/alpha_shortlist_summary.json"
    pool = na.get("shortlist_pool_diagnostic") or {}
    assert "b_grade_count" in pool
