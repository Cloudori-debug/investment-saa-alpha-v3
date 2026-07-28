"""Operational target integrity — idempotency, user superset, restore policy."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.alpha.target_portfolio_guard import (
    _content_hash,
    _read_csv_rows,
    auto_restore_operational_target_if_needed,
    evaluate_target_guard,
    operational_target_path,
    operational_tickers_not_in_user,
    restore_target_from_user_baseline,
    user_target_portfolio_path,
    write_target_guard_diff,
)
from src.alpha.target_portfolio_proposal import write_target_portfolio_proposal
from src.data_loader import write_target_portfolio
from src.models import TargetRow
from src.validation.bundle_consistency import (
    apply_post_restore_conservative_lock,
    build_health_snapshot_id,
    verify_bundle_snapshot_alignment,
)


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


def test_operational_target_hash_stable_across_two_guard_evaluations(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    rows = [_row("005830", 10.0), _row("021240", 8.0)]
    _write_target(data / "user_target_portfolio.csv", rows)
    _write_target(data / "target_portfolio.csv", rows)
    h1 = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    evaluate_target_guard(data, out)
    write_target_portfolio_proposal(
        [TargetRow.model_validate(_row("030190", 0.7))],
        out,
        source="test",
    )
    evaluate_target_guard(data, out)
    h2 = _content_hash(_read_csv_rows(data / "target_portfolio.csv"))
    assert h1 == h2


def test_proposal_write_does_not_touch_operational_target(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    user_rows = [_row("005830", 10.0)]
    _write_target(data / "user_target_portfolio.csv", user_rows)
    _write_target(data / "target_portfolio.csv", user_rows)
    before = (data / "target_portfolio.csv").read_bytes()
    proposal_rows = [
        TargetRow.model_validate(_row("005830", 10.0)),
        TargetRow.model_validate(_row("030190", 0.7)),
    ]
    write_target_portfolio_proposal(proposal_rows, out, source="test")
    write_target_guard_diff(data, out)
    after = (data / "target_portfolio.csv").read_bytes()
    assert before == after
    assert operational_tickers_not_in_user(data) == []


def test_operational_tickers_must_be_subset_of_user(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0), _row("030190", 0.7)])
    assert operational_tickers_not_in_user(data) == ["030190"]


def test_auto_restore_then_conservative_lock(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0), _row("030190", 0.7)])
    (data / "target_portfolio_write_guard.json").write_text('{"operational_target_hash": "stale"}', encoding="utf-8")
    _write_target(out / "proposals" / "target_portfolio_proposal.csv", [_row("030190", 0.7)])

    meta = auto_restore_operational_target_if_needed(data, out)
    assert meta["restored"] is True
    assert meta["post_severity"] == "PASS"
    assert operational_tickers_not_in_user(data) == []

    final = {
        "system_status": "GREEN",
        "execution_scope": "ETF_ONLY",
        "allowed_actions": [{"ticker": "035420", "action": "Buy-allowed", "allowed_size_pct": 2.0}],
        "final_trade_list": [],
        "execution_permissions": {},
    }
    locked = apply_post_restore_conservative_lock(final, meta)
    assert locked["target_restore_occurred"] is True
    assert locked["system_status"] == "YELLOW"
    assert not locked["allowed_actions"]


def test_health_snapshot_id_deterministic() -> None:
    a = build_health_snapshot_id(run_id="r1", target_hash="abc", health_overall="pass", guard_severity="PASS")
    b = build_health_snapshot_id(run_id="r1", target_hash="abc", health_overall="pass", guard_severity="PASS")
    c = build_health_snapshot_id(run_id="r2", target_hash="abc", health_overall="pass", guard_severity="PASS")
    assert a == b
    assert a != c


@pytest.mark.skipif(
    not Path(__file__).resolve().parents[1].joinpath("outputs", "system_health.json").exists(),
    reason="outputs bundle not present",
)
def test_live_bundle_snapshot_alignment() -> None:
    out = Path(__file__).resolve().parents[1] / "outputs"
    result = verify_bundle_snapshot_alignment(out)
    assert result["aligned"], result["issues"]
