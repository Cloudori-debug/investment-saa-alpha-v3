"""Smoke tests for home decision boards (①②③)."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path


def test_build_home_decision_boards_empty(tmp_path: Path):
    from alpha_system.ui.services.home_decision_boards import (
        build_home_decision_boards,
        combined_as_table,
        holdings_as_table,
        proposals_as_table,
    )

    (tmp_path / "data").mkdir()
    ctx = SimpleNamespace(
        root=tmp_path,
        portfolio_rows=[],
        ops_portfolio_rows=[],
        scoreboard_rows=[],
        as_of=None,
    )
    boards = build_home_decision_boards(ctx)
    assert boards.combined == ()
    assert boards.holdings == ()
    assert boards.proposals == ()
    assert combined_as_table([]) == []
    assert holdings_as_table([]) == []
    assert proposals_as_table([]) == []


def test_combined_merges_held_and_proposal(tmp_path: Path):
    from alpha_system.ui.services.home_decision_boards import build_home_decision_boards

    (tmp_path / "data").mkdir()
    # minimal positions for actual map
    (tmp_path / "data" / "positions.csv").write_text(
        "ticker,name,asset_group,quantity,current_value\n"
        "005930,삼성전자,kr_alpha,10,1000000\n",
        encoding="utf-8",
    )
    ctx = SimpleNamespace(
        root=tmp_path,
        portfolio_rows=[
            SimpleNamespace(
                ticker="000660",
                name="SK하이닉스",
                weight_pct=10.0,
                total_score=80.0,
                ops_signal="hold",
                ops_signal_label="유지",
                ops_signal_detail="",
            )
        ],
        ops_portfolio_rows=[
            SimpleNamespace(
                ticker="005930",
                name="삼성전자",
                weight_pct=50.0,
                quantity=10,
                current_value=1000000,
            )
        ],
        scoreboard_rows=[],
        as_of=None,
    )
    boards = build_home_decision_boards(ctx)
    roles = {r.ticker: r.role for r in boards.combined}
    assert roles.get("005930") == "보유"
    assert roles.get("000660") == "제안"
    assert any(r.ticker == "005930" for r in boards.holdings)
    assert any(r.ticker == "000660" for r in boards.proposals)
