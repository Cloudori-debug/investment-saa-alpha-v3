"""Tests for alpha_gate_diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.alpha_gate_diagnostics import (
    build_alpha_gate_diagnostics,
    write_alpha_gate_diagnostics,
)


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def test_alpha_gate_diagnostics_from_outputs() -> None:
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    out = root / "outputs"
    if not (out / "gpt_context.json").exists():
        return

    doc = build_alpha_gate_diagnostics(data, out)
    assert doc["alpha_gate_status"]
    assert doc["alpha_gate_reason_summary"]
    assert isinstance(doc["primary_alpha_blockers"], list)
    assert isinstance(doc["secondary_alpha_blockers"], list)
    assert doc["tier2_provenance_status"]
    assert "gpt_context_candidate_count" in doc
    assert "gpt_context_zero_classification" in doc
    assert doc["pit_data_status"]
    assert doc["fundamental_data_status"]
    assert doc["sector_coverage_status"]
    assert doc["flow_data_status"]
    assert doc["recommended_fix"]

    if doc["alpha_gate_status"] == "YELLOW":
        assert doc["alpha_gate_reason_summary"]
        assert doc["primary_alpha_blockers"] or doc["secondary_alpha_blockers"]


def test_tier2_stale_fields_have_source(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "tier2_provenance.json").write_text(
        json.dumps({
            "as_of": "2026-07-06",
            "fields": {
                "cpi_us_yoy": {
                    "source": "fred:CPIAUCSL",
                    "last_updated": "2026-05-01",
                    "stale_business_days": 46,
                },
            },
        }),
        encoding="utf-8",
    )
    _write_json(out / "gpt_context.json", {
        "as_of": "2026-07-03",
        "alpha_data_gate": "YELLOW",
        "data_gate": "YELLOW",
        "top_candidates": [],
        "data_limitations": [],
        "excluded_summary": {},
        "execution_scope": "ETF_ONLY",
        "alpha_trade_permission": "BLOCK_NEW_BUY",
    })
    _write_json(out / "system_health.json", {"checks": []})
    _write_json(out / "acceptance_report.json", {"execution_scope": "ETF_ONLY", "items": []})
    _write_json(out / "final_execution_decision.json", {"execution_scope": "ETF_ONLY"})

    doc = write_alpha_gate_diagnostics(data, out)
    assert (out / "alpha_gate_diagnostics.json").exists()
    stale = doc["stale_tier2_fields"]
    assert stale
    assert stale[0]["stale_field"] == "cpi_us_yoy"
    assert stale[0]["source_file"] == "data/tier2_provenance.json"
    assert stale[0]["last_updated"] == "2026-05-01"
    assert doc["gpt_context_zero_classification"]["classification"]


def test_gpt_context_zero_classifies_selection_empty(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_json(out / "gpt_context.json", {
        "alpha_data_gate": "YELLOW",
        "top_candidates": [],
        "shortlist_meta": {"shortlist_count": 0},
        "data_limitations": ["숏리스트 0종"],
        "excluded_summary": {},
        "execution_scope": "ETF_ONLY",
        "alpha_trade_permission": "BLOCK_NEW_BUY",
    })
    import csv

    with (out / "alpha_scored_universe.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "grade"])
        w.writerow(["005930", "B"])
        w.writerow(["000660", "B"])
    _write_json(out / "system_health.json", {"checks": []})
    _write_json(out / "acceptance_report.json", {"items": []})
    _write_json(out / "final_execution_decision.json", {})

    doc = build_alpha_gate_diagnostics(data, out)
    assert doc["b_grade_count"] == 2
    assert doc["gpt_context_candidate_count"] == 0
    cls = doc["gpt_context_zero_classification"]["classification"]
    assert cls == "selection_pool_empty_despite_b_grade"
