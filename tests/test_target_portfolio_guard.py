"""target_portfolio_guard reason classification, severity, and execution blocks."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.alpha.target_portfolio_guard import (
    RECOVERY_GUIDE_KO,
    apply_target_guard_to_actions,
    apply_target_guard_to_permissions,
    build_target_guard_diff_rows,
    evaluate_target_guard,
    write_target_guard_diff,
)
from src.execution_permissions import build_execution_permissions
from src.models import GapRow, TradeAction


def _write_target(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _base_row(ticker: str, weight: float, name: str = "Test") -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def _setup_guard(tmp_path: Path, *, user_rows: list[dict], op_rows: list[dict], proposal_rows: list[dict] | None = None) -> Path:
    from src.alpha.target_portfolio_guard import _content_hash, _read_csv_rows

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "outputs"
    data_dir.mkdir()
    out_dir.mkdir()
    _write_target(data_dir / "user_target_portfolio.csv", user_rows)
    _write_target(data_dir / "target_portfolio.csv", op_rows)
    if proposal_rows is not None:
        _write_target(out_dir / "target_portfolio_proposal.csv", proposal_rows)
    guard = data_dir / "target_portfolio_write_guard.json"
    op_hash = _content_hash(_read_csv_rows(data_dir / "target_portfolio.csv"))
    guard.write_text(f'{{"operational_target_hash": "{op_hash}"}}', encoding="utf-8")
    return data_dir


def test_system_proposal_leak_escalates_fail(tmp_path: Path) -> None:
    data_dir = _setup_guard(
        tmp_path,
        user_rows=[_base_row("005830", 10.0, "DB손해보험")],
        op_rows=[
            _base_row("005830", 10.0, "DB손해보험"),
            _base_row("030190", 0.7, "NICE평가정보"),
        ],
        proposal_rows=[_base_row("030190", 0.7, "NICE평가정보")],
    )
    guard = data_dir / "target_portfolio_write_guard.json"
    guard.write_text('{"operational_target_hash": "stale-prev-hash"}', encoding="utf-8")
    detail = evaluate_target_guard(data_dir, tmp_path / "outputs")
    assert detail["severity"] == "FAIL"
    assert detail["system_proposal_leak_count"] >= 1
    assert detail["status"] == "fail"
    assert RECOVERY_GUIDE_KO in detail.get("recovery_guide", "")


def test_unknown_material_escalates_fail(tmp_path: Path) -> None:
    data_dir = _setup_guard(
        tmp_path,
        user_rows=[_base_row("005830", 10.0)],
        op_rows=[_base_row("005830", 15.0)],
        proposal_rows=[],
    )
    guard = data_dir / "target_portfolio_write_guard.json"
    guard.write_text('{"operational_target_hash": "stale-prev-hash"}', encoding="utf-8")
    detail = evaluate_target_guard(data_dir, tmp_path / "outputs")
    assert detail["severity"] == "FAIL"
    assert detail["unknown_material_count"] >= 1


def test_formatting_only_does_not_warn(tmp_path: Path) -> None:
    data_dir = _setup_guard(
        tmp_path,
        user_rows=[_base_row("005830", 10.0)],
        op_rows=[_base_row("005830", 10.0004)],
    )
    rows = build_target_guard_diff_rows(data_dir, tmp_path / "outputs")
    assert not rows or all(r["reason"] == "formatting_only" for r in rows)
    detail = evaluate_target_guard(data_dir, tmp_path / "outputs")
    assert detail["severity"] == "PASS"


def test_approved_change_passes(tmp_path: Path) -> None:
    data_dir = _setup_guard(
        tmp_path,
        user_rows=[_base_row("005830", 10.0)],
        op_rows=[_base_row("005830", 15.0)],
    )
    guard_path = data_dir / "target_portfolio_write_guard.json"
    guard_path.write_text(
        '{"operational_target_hash": "prevhash", "approval_flag": true, "last_approved_write_at": "2026-07-02"}',
        encoding="utf-8",
    )
    detail = evaluate_target_guard(data_dir, tmp_path / "outputs")
    rows = build_target_guard_diff_rows(data_dir, tmp_path / "outputs")
    assert detail["severity"] == "PASS"
    assert rows and all(r["reason"] == "approved_change" for r in rows)


def test_ticker_resolution_change_warn_only(tmp_path: Path) -> None:
    user = _base_row("005830", 10.0, "DB손해보험")
    op = dict(user)
    op["name"] = "DB Insurance"
    data_dir = _setup_guard(tmp_path, user_rows=[user], op_rows=[op])
    rows = build_target_guard_diff_rows(data_dir, tmp_path / "outputs")
    assert rows
    assert rows[0]["reason"] == "ticker_resolution_change"
    detail = evaluate_target_guard(data_dir, tmp_path / "outputs")
    assert detail["severity"] == "WARN"


def test_target_guard_fail_blocks_buy_add_rebalance_replace() -> None:
    trade, pos = apply_target_guard_to_permissions("ALLOW_NEW", "EXECUTABLE", guard_severity="FAIL")
    assert trade == "BLOCK_ALL"
    assert pos == "RISK_REDUCE_ONLY"

    perms = build_execution_permissions(
        execution_scope="FULL_WITH_ALPHA",
        alpha_trade_permission=trade,
        alpha_position_action=pos,
        alpha_price_action="ALPHA_OK",
        restricted_modes=["TARGET_PORTFOLIO_GUARD_FAIL"],
        health_gate="YELLOW",
        core_price_gate_status="pass",
        alpha_price_gate_status="pass",
        data_gate="GREEN",
        portfolio_gate="GREEN",
        alpha_gate="GREEN",
        target_guard_severity="FAIL",
    )
    blocked = set(perms["blocked_capabilities"])
    assert "KR_ALPHA_NEW_BUY" in blocked
    assert "KR_ALPHA_ADD" in blocked
    assert "KR_ALPHA_REPLACE" in blocked
    assert "ETF_REBALANCE" in blocked


def test_target_guard_fail_allows_hold_park_only() -> None:
    gap_rows = [
        GapRow(
            ticker="005830", name="DB손해보험", asset_group="kr_alpha",
            current_weight=12.0, target_weight=10.0, gap=2.0,
            min_weight=0, max_weight=20, status="Overweight", in_target=True,
        ),
        GapRow(
            ticker="069500", name="KODEX200", asset_group="domestic_beta",
            current_weight=5.0, target_weight=5.0, gap=0.0,
            min_weight=0, max_weight=20, status="Within band", in_target=True,
        ),
    ]
    actions = [
        TradeAction(ticker="005830", name="DB손해보험", action="Trim", reason="과체중", allowed_size_pct=-2.0, priority="High"),
        TradeAction(ticker="005830", name="DB손해보험", action="Replace", reason="교체", allowed_size_pct=0, priority="High"),
        TradeAction(ticker="035420", name="NAVER", action="Buy-allowed", reason="신규", allowed_size_pct=2.0, priority="Medium"),
        TradeAction(ticker="069500", name="KODEX200", action="Hold", reason="monitor", allowed_size_pct=0, priority="Low"),
        TradeAction(ticker="CASH", name="Cash", action="Park", reason="park", allowed_size_pct=0, priority="Low"),
        TradeAction(
            ticker="071050", name="한국금융지주", action="Trim",
            reason="kr_alpha 리스크 축소", allowed_size_pct=-1.5, priority="High",
        ),
    ]
    executable, review = apply_target_guard_to_actions(actions, gap_rows, guard_severity="FAIL")
    by_ticker = {a.ticker: a for a in executable}
    assert by_ticker["005830"].action == "Review-only"
    assert by_ticker["035420"].action == "Review-only"
    assert by_ticker["069500"].action == "Hold"
    assert by_ticker["CASH"].action == "Park"
    assert by_ticker["071050"].action == "Trim"
    assert len(review) >= 3


def test_write_target_guard_diff_includes_severity(tmp_path: Path) -> None:
    data_dir = _setup_guard(
        tmp_path,
        user_rows=[_base_row("005830", 10.0)],
        op_rows=[_base_row("005830", 10.0), _base_row("030190", 0.7, "NICE")],
        proposal_rows=[_base_row("030190", 0.7, "NICE")],
    )
    out = tmp_path / "outputs"
    path = write_target_guard_diff(data_dir, out)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert any(r["reason"] == "system_proposal_leak" for r in rows)
    assert "severity" in rows[0]
