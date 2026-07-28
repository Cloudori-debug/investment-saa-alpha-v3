from __future__ import annotations

import json
from pathlib import Path

from src.validation.core_etf_blocking_duration import (
    compute_core_etf_blocking_duration,
    format_core_etf_blocking_duration_line,
    write_core_etf_blocking_duration,
)


def _write_log(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_restricted_streak_three_days(tmp_path: Path) -> None:
    log = tmp_path / "decision_log.jsonl"
    _write_log(log, [
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-06",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "target_guard_conflict_detected": False,
            "execution_scope": "ETF_ONLY",
        },
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-07",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "target_guard_conflict_detected": False,
            "execution_scope": "ETF_ONLY",
        },
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-08",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "target_guard_conflict_detected": True,
            "execution_scope": "ETF_ONLY",
        },
    ])
    doc = compute_core_etf_blocking_duration(
        log,
        "2026-07-08",
        lookback_days=30,
        core_etf_diagnostics={
            "core_etf_permission": "RESTRICTED",
            "eligible_etf_underweight_count": 11,
            "restriction_reasons": ["data_gate=YELLOW→core_etf_REVIEW_ONLY"],
        },
    )
    assert doc["core_etf_restricted_days_current_streak"] == 3
    assert doc["core_etf_restricted_days_last_30d"] == 3
    assert doc["eligible_etf_underweight_count_today"] == 11
    assert doc["dominant_restriction_reason"]
    assert "gate/policy_cap 미변경" in doc["note"]


def test_streak_breaks_on_green_day(tmp_path: Path) -> None:
    log = tmp_path / "decision_log.jsonl"
    _write_log(log, [
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-06",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "execution_scope": "ETF_ONLY",
        },
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-07",
            "health_gate": "GREEN",
            "acceptance_overall": "GREEN",
            "operational_status": "GREEN",
            "execution_scope": "ETF_ONLY",
            "target_guard_conflict_detected": False,
        },
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-08",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "execution_scope": "ETF_ONLY",
        },
    ])
    doc = compute_core_etf_blocking_duration(log, "2026-07-08", lookback_days=30)
    assert doc["core_etf_restricted_days_current_streak"] == 1
    assert doc["core_etf_restricted_days_last_30d"] == 2


def test_write_and_format_line(tmp_path: Path) -> None:
    log = tmp_path / "decision_log.jsonl"
    _write_log(log, [
        {
            "event": "bundle_reconciliation",
            "as_of": "2026-07-08",
            "health_gate": "YELLOW",
            "acceptance_overall": "YELLOW",
            "operational_status": "YELLOW",
            "execution_scope": "ETF_ONLY",
        },
    ])
    (tmp_path / "core_etf_permission_diagnostics.json").write_text(
        json.dumps({
            "core_etf_permission": "RESTRICTED",
            "eligible_etf_underweight_count": 11,
            "restriction_reasons": ["policy_cap_active", "data_gate=YELLOW"],
        }),
        encoding="utf-8",
    )
    doc = write_core_etf_blocking_duration(
        tmp_path,
        as_of="2026-07-08",
        decision_log_path=log,
    )
    assert (tmp_path / "core_etf_blocking_duration.json").exists()
    line = format_core_etf_blocking_duration_line(doc)
    assert "Core ETF 잠김 지속" in line
    assert "11건" in line
    assert "Actual Buy Allowed 불변" in line
