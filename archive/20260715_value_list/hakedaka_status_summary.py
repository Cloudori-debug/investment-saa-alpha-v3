from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json

HAKEDAKA_STATUS_DISCLAIMER = (
    "Shadow diagnostic only. evidence_ready ≠ investment or execution actionable. "
    "Execution authority remains v1.0.2 trade_actions/allowed_actions only."
)


def _evidence_ready_count(coverage: dict[str, Any] | None) -> int:
    if not coverage:
        return 0
    return int(
        coverage.get("evidence_ready_candidate_count")
        or coverage.get("actionable_candidate_count")
        or 0
    )


def build_latest_hakedaka_status(output_dir: Path) -> dict[str, Any]:
    """Aggregate hakedaka pipeline state into a single shadow status snapshot."""
    coverage = read_output_json(output_dir / "hakedaka_coverage_audit.json")
    phase4h1 = read_output_json(output_dir / "hakedaka_phase4h1_report.json")
    phase4i1 = read_output_json(output_dir / "hakedaka_phase4i1_report.json")
    phase4i = read_output_json(output_dir / "hakedaka_phase4i_report.json")

    cov = (coverage or {}).get("coverage") or {}
    financial_critical = bool((coverage or {}).get("financial_coverage_critical", False))
    data_ready = bool(coverage) and not financial_critical and float(cov.get("ocf_coverage") or 0) >= 70

    h1_summary = (phase4h1 or {}).get("summary") or {}
    parse_suspect = int(h1_summary.get("parse_suspect_count") or 0)
    catalyst_extraction_ready = bool(phase4h1) and parse_suspect == 0

    i1_summary = (phase4i1 or {}).get("summary") or {}
    pending_count = int(i1_summary.get("pending_count") or (phase4i or {}).get("summary", {}).get("pending_count") or 0)
    available_count = int(i1_summary.get("available_count") or (phase4i or {}).get("summary", {}).get("available_count") or 0)
    forward_return_pending = pending_count > 0 and available_count == 0
    alignment_pass = bool(i1_summary.get("alignment_pass", False))

    effective_date = i1_summary.get("effective_signal_date") or ""
    next_checkpoint = ""
    tracker_path = output_dir / "hakedaka_forward_return_tracker.csv"
    if tracker_path.exists():
        import csv
        with tracker_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                next_checkpoint = row.get("forward_target_date_5d") or next_checkpoint
                if next_checkpoint:
                    break

    as_of = (
        (coverage or {}).get("as_of")
        or i1_summary.get("signal_calendar_date")
        or (phase4i or {}).get("as_of")
        or ""
    )

    return {
        "as_of": as_of,
        "mode": "shadow_only",
        "disclaimer": HAKEDAKA_STATUS_DISCLAIMER,
        "data_ready": data_ready,
        "catalyst_extraction_ready": catalyst_extraction_ready,
        "forward_return_pending": forward_return_pending,
        "forward_return_alignment_pass": alignment_pass,
        "effective_signal_date": effective_date,
        "next_forward_checkpoint_5d": next_checkpoint,
        "execution_actionable": False,
        "execution_actionable_count": 0,
        "investment_actionable": False,
        "investment_actionable_count": 0,
        "evidence_ready_candidate_count": _evidence_ready_count(coverage),
        "execution_authority": "none",
        "shadow_only": True,
    }


def write_latest_hakedaka_status(output_dir: Path) -> dict[str, Any]:
    status = build_latest_hakedaka_status(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "hakedaka_latest_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return status
