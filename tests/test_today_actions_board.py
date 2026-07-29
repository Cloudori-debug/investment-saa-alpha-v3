"""Today action board — merge exit/band/MHM."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alpha_system.ui.services.today_actions_board import (
    build_today_action_board,
    today_actions_as_table,
)


def test_today_actions_priority_exit_over_band(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,target_weight\n005830,DB손보,kr_alpha,5.0\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "as_of,regime\n2026-07-28,CRISIS\n",
        encoding="utf-8",
    )
    # Copy default alpha policy if needed
    import shutil

    src = Path("data/alpha_book_ops.yaml")
    if src.exists():
        shutil.copy(src, data / "alpha_book_ops.yaml")

    proposal = [
        SimpleNamespace(
            ticker="005830",
            name="DB손보",
            weight_pct=18.0,
            initial_weight_pct=10.0,
            ops_signal="trim",
            ops_signal_label="줄이기",
            ops_signal_detail="목표가 근접",
        )
    ]
    ops = [
        SimpleNamespace(
            ticker="005830",
            name="DB손보",
            weight_pct=90.0,
            quantity=10,
            current_value=1_000_000,
        )
    ]
    ctx = SimpleNamespace(
        root=tmp_path,
        as_of=date(2026, 7, 28),
        ops_portfolio_rows=ops,
        portfolio_rows=proposal,
    )
    board = build_today_action_board(ctx)
    assert board.rows
    row = next(r for r in board.rows if r.ticker == "005830")
    assert row.priority == 1
    assert "익절" in row.priority_label
    table = today_actions_as_table(board.rows)
    assert table[0]["우선"].startswith("1")
