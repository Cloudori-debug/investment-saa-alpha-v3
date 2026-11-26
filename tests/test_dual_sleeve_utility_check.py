"""Soft·행동주의 이원화 효용 검증."""

from __future__ import annotations

from pathlib import Path

from alpha_system.shadow.dual_sleeve_utility_check import (
    WRITES_TARGET,
    build_utility_board,
)

ROOT = Path(__file__).resolve().parents[1]


def test_utility_board_review_only() -> None:
    board = build_utility_board(ROOT, market="KOSPI")
    assert board.writes_target is False
    assert WRITES_TARGET is False
    assert board.verdict["charter_keep_dual"] is True
    assert "soft_only_ew" in board.portfolios
    assert "dual_50_50" in board.portfolios
    assert board.verdict["status"] in {
        "supports_dual",
        "neutral_dual",
        "weak_diversify",
        "incomplete",
        "design_breach",
    }
