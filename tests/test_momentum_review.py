"""Momentum Review-only grades — unit tests (no UI)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alpha_system.ui.services.momentum_review import (
    classify_momentum_grade,
    build_momentum_review_board,
)


def test_classify_go() -> None:
    g, _ = classify_momentum_grade(
        ret_12_1=0.18,
        ret_6=0.10,
        ret_3=0.04,
        cross_pct=72.0,
        vol_high=False,
        crisis=False,
    )
    assert g == "GO"


def test_classify_wait_down() -> None:
    g, _ = classify_momentum_grade(
        ret_12_1=-0.04,
        ret_6=-0.06,
        ret_3=-0.02,
        cross_pct=28.0,
        vol_high=False,
        crisis=False,
    )
    assert g == "WAIT"


def test_classify_slow_mid_cross() -> None:
    g, _ = classify_momentum_grade(
        ret_12_1=0.09,
        ret_6=0.02,
        ret_3=-0.02,
        cross_pct=55.0,
        vol_high=False,
        crisis=False,
    )
    assert g == "SLOW"


def test_classify_cut_pace_vol() -> None:
    g, _ = classify_momentum_grade(
        ret_12_1=0.22,
        ret_6=0.19,
        ret_3=0.08,
        cross_pct=81.0,
        vol_high=True,
        crisis=False,
    )
    assert g == "CUT_PACE"


def test_classify_crisis_overrides_go() -> None:
    g, _ = classify_momentum_grade(
        ret_12_1=0.20,
        ret_6=0.10,
        ret_3=0.05,
        cross_pct=80.0,
        vol_high=False,
        crisis=True,
    )
    assert g == "CUT_PACE"


def test_board_builds_from_prices(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "market_indicators.csv").write_text(
        "as_of,regime\n2026-07-28,RISK_ON\n",
        encoding="utf-8",
    )
    (data / "prices.csv").write_text(
        "date,ticker,close,return_1m,return_3m,return_6m,return_12m,"
        "return_12m_ex_1m,volatility_60d\n"
        "2026-07-27,030200,50000,0.02,0.04,0.11,0.20,0.45,0.02\n"
        "2026-07-27,005830,100000,-0.03,-0.02,-0.06,-0.08,-0.04,0.02\n"
        "2026-07-27,021240,60000,0.01,-0.02,0.02,0.10,0.09,0.02\n"
        "2026-07-27,999901,1000,0.0,0.0,0.0,0.0,0.50,0.10\n"
        "2026-07-27,999902,1000,0.0,0.0,0.0,0.0,0.40,0.09\n"
        "2026-07-27,999903,1000,0.0,0.0,0.0,0.0,0.30,0.08\n"
        "2026-07-27,999904,1000,0.0,0.0,0.0,0.0,0.20,0.07\n"
        "2026-07-27,999905,1000,0.0,0.0,0.0,0.0,0.10,0.06\n"
        "2026-07-27,999906,1000,0.0,0.0,0.0,0.0,0.00,0.05\n"
        "2026-07-27,999907,1000,0.0,0.0,0.0,0.0,-0.10,0.04\n",
        encoding="utf-8",
    )
    ops = [
        SimpleNamespace(ticker="030200", name="KT"),
        SimpleNamespace(ticker="005830", name="DB손보"),
        SimpleNamespace(ticker="021240", name="코웨이"),
    ]
    ctx = SimpleNamespace(
        root=tmp_path,
        as_of=date(2026, 7, 28),
        ops_portfolio_rows=ops,
        portfolio_rows=[],
    )
    board = build_momentum_review_board(ctx, as_of=date(2026, 7, 28))
    assert board.price_as_of == "2026-07-27"
    by_tk = {i.ticker: i for i in board.items}
    assert by_tk["030200"].grade == "GO"
    assert by_tk["005830"].grade == "WAIT"
    assert by_tk["005830"].execute_allowed is False
    assert by_tk["021240"].grade in ("SLOW", "GO", "WAIT")
    assert by_tk["030200"].execute_allowed is True
    assert "주간" in board.cadence_note or "회차" in board.cadence_note
