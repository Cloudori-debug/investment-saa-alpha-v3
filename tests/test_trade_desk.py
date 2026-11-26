"""Trail gap and the single trade desk."""

from __future__ import annotations

from alpha_system.ui.services.trade_desk import (
    ACTION_BUY,
    ACTION_CLEAR,
    ACTION_SELL,
    build_trade_desk,
)
from alpha_system.ui.services.trail_exit_signal import gap_cross_note, trail_path_state


def test_one_step_is_not_a_jump() -> None:
    assert gap_cross_note(100, 87, 100) is None
    assert gap_cross_note(88, 79, 100) is None


def test_ff_style_day_skips_trim_and_half() -> None:
    note = gap_cross_note(80500, 61800, 86100)
    assert note is not None
    assert "줄이기" in note
    assert "환금" in note
    assert "전량" in note
    band, drawdown, jump = trail_path_state([86100, 80500, 61800, 58900])
    assert band == 3
    assert jump is not None
    assert "하루 점프" in jump
    assert drawdown > 0.28


def test_new_high_clears_an_old_jump() -> None:
    band, _, jump = trail_path_state([100, 70, 110])
    assert band == 0
    assert jump is None


def test_desk_sells_a_name_the_score_book_still_holds() -> None:
    rows = build_trade_desk(
        proposal=[("383220", "F&F", 58900)],
        holdings=[("383220", "F&F", 0), ("005930", "삼성전자", 10)],
        closes_by_ticker={"383220": [86100, 80500, 61800]},
        live_price={"383220": 58900},
    )
    by_tk = {row.ticker: row for row in rows}
    ff = by_tk["383220"]
    assert ff.action == ACTION_SELL
    assert ff.proposal == "예"
    assert ff.held == "수량 0"
    assert "하루 점프" in ff.signal
    assert "제안에는 있음" in ff.signal
    held = by_tk["005930"]
    assert held.action == ACTION_SELL
    assert held.proposal == "—"
    assert held.held == "보유"


def test_checked_flat_name_outside_proposal_is_cleared() -> None:
    rows = build_trade_desk(
        proposal=[],
        holdings=[("383220", "F&F", 0)],
        closes_by_ticker={"383220": [86100, 80500, 61800, 58900]},
    )
    assert rows[0].action == ACTION_CLEAR
    assert "하루 점프" in rows[0].signal
    assert "수량 0" in rows[0].signal


def test_desk_buy_when_proposed_and_flat() -> None:
    rows = build_trade_desk(
        proposal=[("000001", "A", 1000)],
        holdings=[],
        closes_by_ticker={"000001": [1000, 1010, 1005]},
    )
    assert rows[0].action == ACTION_BUY
    assert rows[0].held == "—"


def test_desk_never_held_soft_stays_buy_despite_trail_drawdown() -> None:
    """미보유 Soft 후보는 고점낙폭이 커도 팔기가 아니라 사기(+참고)."""
    rows = build_trade_desk(
        proposal=[("383220", "F&F", 58900)],
        holdings=[],
        closes_by_ticker={"383220": [86100, 80500, 61800]},
        live_price={"383220": 58900},
    )
    assert len(rows) == 1
    assert rows[0].action == ACTION_BUY
    assert rows[0].held == "—"
    assert "신규" in rows[0].signal
    assert "참고" in rows[0].signal
    assert "제안에는 있음" not in rows[0].signal
