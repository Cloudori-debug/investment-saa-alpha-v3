"""Hakedaka latest status summary tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.value_list.hakedaka_status_summary import build_latest_hakedaka_status, write_latest_hakedaka_status


def test_latest_hakedaka_status_actionable_distinction(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "hakedaka_coverage_audit.json").write_text(json.dumps({
        "as_of": "2026-06-28",
        "financial_coverage_critical": False,
        "coverage": {"ocf_coverage": 100.0},
        "evidence_ready_candidate_count": 44,
        "execution_actionable_count": 0,
        "investment_actionable_count": 0,
    }), encoding="utf-8")
    (out / "hakedaka_phase4h1_report.json").write_text(json.dumps({
        "summary": {"parse_suspect_count": 0},
    }), encoding="utf-8")
    (out / "hakedaka_phase4i1_report.json").write_text(json.dumps({
        "summary": {
            "alignment_pass": True,
            "pending_count": 26,
            "available_count": 0,
            "effective_signal_date": "2026-06-26",
        },
    }), encoding="utf-8")

    status = build_latest_hakedaka_status(out)
    assert status["evidence_ready_candidate_count"] == 44
    assert status["execution_actionable_count"] == 0
    assert status["investment_actionable_count"] == 0
    assert status["investment_actionable"] is False
    assert status["forward_return_pending"] is True
    assert status["data_ready"] is True

    written = write_latest_hakedaka_status(out)
    assert (out / "hakedaka_latest_status.json").exists()
    assert written["catalyst_extraction_ready"] is True
