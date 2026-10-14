"""Absolute name-unit weight-action — no holdings CSV ratio."""

from __future__ import annotations

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.portfolio_widgets import (
    _chart_flow_synth_html,
    _mid_book_cue_html,
    _mid_buy_parts,
    _mid_exit_parts,
)
from alpha_system.ui.services.weight_action import (
    board_items,
    resolve_weight_action,
    weight_action_board_html,
    weight_action_html,
)


def _mid(**kw) -> PortfolioRow:
    extra = {"book": "ops", **kw.pop("extra", {})}
    return PortfolioRow(
        ticker=kw.get("ticker", "005930"),
        name=kw.get("name", "삼성"),
        weight_pct=kw.get("weight_pct", 0.0),
        initial_weight_pct=kw.get("initial_weight_pct", kw.get("weight_pct", 10.0)),
        avg_price=100.0,
        current_price=kw.get("current_price", 100.0),
        target_price=kw.get("target_price", 200.0),
        target_progress=50.0,
        remaining_upside_pct=None,
        has_target=kw.get("has_target", True),
        target_detail="test",
        cap_pct=15.0,
        cap_headroom_pct=5.0,
        cap_near=kw.get("cap_near", False),
        ops_signal=kw.get("ops_signal", "hold"),
        ops_signal_label=kw.get("ops_signal_label", "유지"),
        ops_signal_detail=kw.get("ops_signal_detail", ""),
        ops_trim_pct=kw.get("ops_trim_pct"),
        extra=extra,
    )


def test_cash_half_absolute() -> None:
    row = _mid(
        ops_signal="cash_half",
        ops_signal_label="환금",
        ops_trim_pct=50,
        weight_pct=10.0,
    )
    act = resolve_weight_action(
        row,
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "cash_half"
    assert act.stance == "매도"
    assert act.move_pct == 50.0
    assert act.delta_pct is None
    assert act.primary == "매도할 50%"
    assert "보유" not in act.body


def test_trim_priority_before_add() -> None:
    row = _mid(
        ops_signal="trim",
        ops_signal_label="줄이기",
        ops_trim_pct=25,
        weight_pct=8.0,
        current_price=100.0,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 좋음",
        now_action="보유·소량만",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "trim"
    assert act.stance == "매도"
    assert act.move_pct == 25.0


def test_add_buy1_shows_cum_ceiling_and_day_cap() -> None:
    """매수1 = 누적 상한 67% · 오늘≤약 33% (당일 67% 매수 아님)."""
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        weight_pct=18.2,
        initial_weight_pct=None,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 좋음",
        now_action="보유·소량만",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "add_ready"
    assert act.stance == "매수"
    assert act.move_pct == 67.0
    assert act.primary == "누적 상한 67% (오늘≤약 33%)"
    assert "보유" not in act.body
    assert "금액은 사람" in act.body
    html = weight_action_html(act)
    assert "누적 상한 67%" in html
    assert "오늘≤약 33%" in html


def test_add_wait_keeps_ceiling_copy() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        weight_pct=4.0,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 약함",
        now_action="보유·소량만",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "add_wait"
    assert act.stance == "유지"
    assert act.move_pct == 67.0
    assert act.primary == "누적 상한 67% (오늘≤약 33%)"


def test_add_wait_when_now_hard_blocks() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 좋음",
        now_action="추매금지",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "add_wait"
    assert act.stance == "유지"
    assert "추매금지" not in act.body


def test_shrink_review_does_not_collapse_add() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        weight_pct=0.0,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 좋음",
        now_action="축소·교체 검토",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.kind == "add_ready"
    assert act.stance == "매수"
    assert act.move_pct == 67.0


def test_board_orders_exit_before_add() -> None:
    cash = _mid(
        ticker="005930",
        name="삼성",
        ops_signal="cash_half",
        ops_signal_label="환금",
        ops_trim_pct=50,
        weight_pct=10.0,
    )
    add = _mid(
        ticker="000660",
        name="하이닉스",
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        weight_pct=0.0,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
        },
    )
    pairs = [
        (
            cash,
            resolve_weight_action(
                cash,
                exit_parts=_mid_exit_parts(cash),
                buy_parts=_mid_buy_parts(cash),
            ),
        ),
        (
            add,
            resolve_weight_action(
                add,
                mom_label="흐름 좋음",
                now_action="보유·소량만",
                exit_parts=_mid_exit_parts(add),
                buy_parts=_mid_buy_parts(add),
            ),
        ),
    ]
    items = board_items(pairs)
    assert items[0].kind == "cash_half"
    assert items[1].kind == "add_ready"
    html = weight_action_board_html(items)
    assert "누적 상한" in html or "오늘≤약" in html
    assert html.index("매도 삼성") < html.index("매수 하이닉스")


def test_synth_puts_weight_before_ops() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "return_6m": 0.05,
        },
    )
    html = _chart_flow_synth_html(row, chart=None, flow_data_dir=None)
    assert "오늘 비중" in html
    assert html.index("오늘 비중") < html.index("1 · 운영")
    assert "유지" in _mid_book_cue_html(row)


def test_synth_compact_hides_layers() -> None:
    row = _mid(
        current_price=100.0,
        ops_signal="hold",
        ops_signal_label="유지",
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "return_6m": 0.05,
        },
    )
    html = _chart_flow_synth_html(
        row, chart=None, flow_data_dir=None, compact=True
    )
    assert "오늘 비중" in html
    assert "pf-review-compact" in html
    assert "1 · 운영" not in html
    assert "2 · 모멘텀" not in html
    assert "3 · 지금" not in html


def test_hold_outside_buy_is_zero() -> None:
    row = _mid(
        current_price=180.0,
        ops_signal="hold",
        ops_signal_label="유지",
        weight_pct=99.0,
        extra={
            "ladder_ok": True,
            "ladder_rungs": [100.0, 125.0, 150.0, 175.0, 200.0],
            "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
            "ladder_over_high": True,
        },
    )
    act = resolve_weight_action(
        row,
        mom_label="흐름 좋음",
        exit_parts=_mid_exit_parts(row),
        buy_parts=_mid_buy_parts(row),
    )
    assert act.stance == "유지"
    assert act.primary == "채울 0%"
    assert act.kind == "hold"
