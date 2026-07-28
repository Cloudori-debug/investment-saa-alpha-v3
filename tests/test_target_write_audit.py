"""Tests for operational target write audit and single entry point."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.alpha.target_portfolio_guard import (
    TargetPortfolioWriteBlockedError,
    _content_hash,
    _read_csv_rows,
    auto_restore_operational_target_if_needed,
    evaluate_target_guard,
    operational_target_path,
    restore_target_from_user_baseline,
    write_target_portfolio_approved,
)
from src.alpha.target_portfolio_proposal import write_target_portfolio_proposal
from src.alpha.target_bridge import apply_proposed_target, propose_target_changes
from src.alpha.target_write_audit import (
    get_last_target_write_audit,
    target_write_audit_path,
    write_operational_target,
)
from src.data_loader import write_target_portfolio
from src.models import TargetRow
from src.validation.bundle_consistency import apply_post_restore_conservative_lock


def _write_target(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _row(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def test_direct_write_target_portfolio_blocked(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "target_portfolio.csv"
    row = TargetRow.model_validate(_row("005830", 10.0))
    with pytest.raises(TargetPortfolioWriteBlockedError):
        write_target_portfolio([row], path)


def test_forbidden_source_blocks_write(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])
    before = (data / "target_portfolio.csv").read_bytes()

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.0)), TargetRow.model_validate(_row("030190", 0.7))],
        source="compass_proposal",
        reason="test forbidden",
        writer_module="test_forbidden",
        output_dir=out,
    )
    assert result.blocked is True
    assert result.success is False
    assert (data / "target_portfolio.csv").read_bytes() == before
    audit = get_last_target_write_audit(out)
    assert audit.get("target_write_allowed") is False
    assert audit.get("event") == "target_write_audit"


def test_approval_bridge_requires_approved_by_user(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 12.0))],
        source="approval_bridge",
        reason="no user flag",
        approved_by_user=False,
        writer_module="test",
        output_dir=out,
    )
    assert result.blocked is True


def test_approval_bridge_write_allowed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 11.0))],
        source="approval_bridge",
        reason="user approved",
        approved_by_user=True,
        writer_module="test",
        output_dir=out,
        run_id="run-test-1",
    )
    assert result.success is True
    guard = evaluate_target_guard(data, out)
    assert guard["severity"] == "PASS"
    assert target_write_audit_path(out).exists()
    audit = get_last_target_write_audit(out)
    assert audit.get("run_id") == "run-test-1"
    assert audit.get("guard_result_after_write") == "PASS"
    assert audit.get("write_material_change_count") == 1
    assert audit.get("changed_rows_after_write") == audit.get("user_op_guard_diff_rows")
    assert audit.get("user_op_guard_diff_rows") == 0  # synced user↔op


def test_proposal_does_not_overwrite_operational_target(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    rows = [_row("005830", 10.0)]
    _write_target(data / "user_target_portfolio.csv", rows)
    _write_target(data / "target_portfolio.csv", rows)
    before = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))

    write_target_portfolio_proposal(
        [TargetRow.model_validate(_row("030190", 0.7))],
        out,
        source="compass_pipeline",
    )
    assert (out / "proposals" / "target_portfolio_proposal.csv").exists()
    after = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    assert before == after


def test_restore_allowed_but_conservative_lock(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0), _row("030190", 0.7)])
    _write_target(out / "proposals" / "target_portfolio_proposal.csv", [_row("030190", 0.7)])

    meta = auto_restore_operational_target_if_needed(data, out)
    assert meta["restored"] is True
    assert meta["post_severity"] == "PASS"

    final = {"system_status": "GREEN", "allowed_actions": [{"action": "Buy-allowed"}], "execution_permissions": {}}
    locked = apply_post_restore_conservative_lock(final, meta)
    assert locked["system_status"] == "YELLOW"
    assert locked["target_restore_occurred"] is True


def test_guard_revalidated_after_write(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    result = write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.0))],
        source="approval_bridge",
        reason="sync",
        approved_by_user=True,
        writer_module="test",
        output_dir=out,
    )
    assert result.guard_after is not None
    assert result.audit.get("proposal_leak_after_write") == 0
    assert result.audit.get("changed_rows_after_write") == 0


def test_audit_in_decision_log_and_audit_file(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])

    write_operational_target(
        data,
        [TargetRow.model_validate(_row("005830", 10.5))],
        source="approval_bridge",
        reason="audit dual log",
        approved_by_user=True,
        writer_module="test",
        output_dir=out,
        run_id="run-d609",
    )
    audit_lines = target_write_audit_path(out).read_text(encoding="utf-8").strip().splitlines()
    assert audit_lines
    audit_ev = json.loads(audit_lines[-1])
    assert audit_ev["run_id"] == "run-d609"

    log_lines = (out / "decision_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    log_events = [json.loads(l) for l in log_lines if json.loads(l).get("event") == "target_write_audit"]
    assert any(ev.get("run_id") == "run-d609" for ev in log_events)


def test_apply_proposed_target_via_approval_bridge(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    current = [
        TargetRow.model_validate(_row("005830", 90.0)),
        TargetRow.model_validate(_row("453340", 10.0)),
    ]
    _write_target(data / "user_target_portfolio.csv", [r.model_dump() for r in current])
    _write_target(data / "target_portfolio.csv", [r.model_dump() for r in current])
    proposal = propose_target_changes(
        current,
        add_candidates=[],
        trim_tickers={"453340"},
        remove_tickers=set(),
    )
    apply_proposed_target(
        proposal,
        operational_target_path(data),
        data_dir=data,
        output_dir=out,
        approved_by="human",
        writer_module="ui.target_approval_actions",
    )
    audit = get_last_target_write_audit(out)
    assert audit.get("target_write_source") == "approval_bridge"
    assert audit.get("target_write_allowed") is True
    assert audit.get("writer_module") == "ui.target_approval_actions"
    assert "write_material_change_count" in audit


def test_count_material_weight_changes_helper() -> None:
    from src.alpha.target_portfolio_guard import count_material_weight_changes

    before = [_row("005830", 10.0), _row("021240", 5.0)]
    after = [_row("005830", 11.0), _row("021240", 5.0), _row("000660", 1.0)]
    assert count_material_weight_changes(before, after) == 2


def test_two_guard_evaluations_same_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    rows = [_row("005830", 10.0), _row("021240", 8.0)]
    _write_target(data / "user_target_portfolio.csv", rows)
    _write_target(data / "target_portfolio.csv", rows)
    h1 = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    evaluate_target_guard(data, out)
    write_target_portfolio_proposal([TargetRow.model_validate(_row("030190", 0.7))], out, source="test")
    evaluate_target_guard(data, out)
    h2 = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    assert h1 == h2
