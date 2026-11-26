"""고이즈미·한국 하케다카 시나리오 Lab (Review-only)."""

from __future__ import annotations

from pathlib import Path

from alpha_system.shadow.koizumi_kr_hakedaka_scenario import (
    SCENARIOS,
    WRITES_TARGET,
    build_scenario_board,
    scenario_table_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def test_scenarios_ordered_intensity() -> None:
    assert SCENARIOS["weak"]["activist_ret"] < SCENARIOS["mid"]["activist_ret"]
    assert SCENARIOS["mid"]["activist_ret"] < SCENARIOS["strong"]["activist_ret"]
    assert SCENARIOS["mid"]["kospi_ret"] == 0.20


def test_board_review_only() -> None:
    board = build_scenario_board(ROOT, market="KOSPI")
    assert board.writes_target is False
    assert WRITES_TARGET is False
    assert board.review_only is True
    assert set(board.scenarios) == {"weak", "mid", "strong"}
    rows = scenario_table_rows(board)
    assert len(rows) == 3
    # 50/50 blend between soft and activist path (or cash 0 if empty)
    mid = board.scenarios["mid"]
    assert mid["blend_50_50_ret"] == round(
        0.5 * mid["soft_ret"] + 0.5 * mid["activist_ret"], 4
    )
