"""Monthly rebalance board — unit tests (no UI)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alpha_system.ui.services.monthly_rebal_board import (
    _band_breach,
    build_monthly_rebal_board,
)


def test_band_breach_relative() -> None:
    ok, _ = _band_breach(5.0, 5.0, band_rel=0.25)
    assert ok is False
    bad, detail = _band_breach(8.0, 5.0, band_rel=0.25)
    assert bad is True
    assert "밴드" in detail


def test_board_crisis_and_band(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,target_weight\n"
        "005830,DB손보,kr_alpha,5.0\n"
        "021240,코웨이,kr_alpha,5.0\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "as_of,regime\n2026-07-28,CRISIS\n",
        encoding="utf-8",
    )
    ops = [
        SimpleNamespace(
            ticker="005830",
            name="DB손보",
            weight_pct=8.0,
            initial_weight_pct=5.0,
            ops_signal="",
            ops_signal_label="",
            ops_signal_detail="",
        )
    ]
    ctx = SimpleNamespace(
        root=tmp_path,
        as_of=date(2026, 7, 28),
        ops_portfolio_rows=ops,
        portfolio_rows=[],
    )
    board = build_monthly_rebal_board(ctx, as_of=date(2026, 7, 28))
    assert board.crisis is True
    keys = {c.key: c for c in board.cards}
    assert keys["crisis"].do_now is True
    assert keys["band"].do_now is True  # crisis allows band rebal now
    assert any(i.ticker == "005830" for i in keys["band"].items)


def test_month_start_without_breach_is_idle(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,target_weight\n005830,DB손보,kr_alpha,5.0\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "as_of,regime\n2026-07-01,RISK_ON\n",
        encoding="utf-8",
    )
    ops = [
        SimpleNamespace(
            ticker="005830",
            name="DB손보",
            weight_pct=5.1,
            initial_weight_pct=5.0,
            ops_signal="",
            ops_signal_label="",
            ops_signal_detail="",
        )
    ]
    ctx = SimpleNamespace(
        root=tmp_path,
        as_of=date(2026, 7, 1),
        ops_portfolio_rows=ops,
        portfolio_rows=[],
    )
    board = build_monthly_rebal_board(ctx, as_of=date(2026, 7, 1))
    assert board.is_month_start_window is True
    assert board.do_now_count == 0
