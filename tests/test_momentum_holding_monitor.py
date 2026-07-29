"""Momentum Holding Monitor — bearing rules & streak."""

from __future__ import annotations

from alpha_system.ui.services.momentum_holding_monitor import (
    classify_bearing,
    compute_upside,
    is_short_weak,
    _weak_streak_from_history,
)


def test_bearing_enter_ok() -> None:
    b, _ = classify_bearing(
        ts_sign="UP",
        xs_pct=70,
        vol_flag=False,
        grade="GO",
        weak_streak=0,
        short_weak=False,
    )
    assert b == "ENTER_OK"


def test_bearing_exit_needs_streak() -> None:
    b1, _ = classify_bearing(
        ts_sign="DOWN",
        xs_pct=20,
        vol_flag=False,
        grade="WAIT",
        weak_streak=2,
        exit_streak_n=5,
    )
    assert b1 == "TRIM_PACE"
    b2, _ = classify_bearing(
        ts_sign="DOWN",
        xs_pct=20,
        vol_flag=False,
        grade="WAIT",
        weak_streak=5,
        exit_streak_n=5,
    )
    assert b2 == "EXIT_REVIEW"


def test_bearing_trim_on_vol() -> None:
    b, _ = classify_bearing(
        ts_sign="UP",
        xs_pct=70,
        vol_flag=True,
        grade="GO",
        weak_streak=0,
    )
    assert b == "TRIM_PACE"


def test_bearing_trim_when_mid_up_but_short_weak() -> None:
    """Semiconductor-style: 12-1 still UP, 1M/3M down → no HOLD_UP."""
    b, reason = classify_bearing(
        ts_sign="UP",
        xs_pct=70,
        vol_flag=False,
        grade="GO",
        weak_streak=0,
        short_weak=True,
    )
    assert b == "TRIM_PACE"
    assert "단기" in reason or "1·3" in reason


def test_upside_blocked_by_short_weak() -> None:
    assert compute_upside(ts_sign="UP", xs_pct=55, short_weak=False) is True
    assert compute_upside(ts_sign="UP", xs_pct=55, short_weak=True) is False


def test_is_short_weak() -> None:
    assert is_short_weak(-0.05, 0.10) is True
    assert is_short_weak(0.02, -0.08) is True
    assert is_short_weak(0.02, 0.05) is False
    assert is_short_weak(None, None) is False


def test_strategy_playbook_scale_in_enter() -> None:
    from alpha_system.ui.services.momentum_holding_monitor import strategy_playbook

    action, detail = strategy_playbook(
        bearing="ENTER_OK",
        source="scale_in",
        short_weak=False,
        vol_flag=False,
        weak_streak=0,
        exit_streak_n=5,
    )
    assert action == "분할매수 진행"
    assert "3거래일" in detail


def test_strategy_playbook_exit() -> None:
    from alpha_system.ui.services.momentum_holding_monitor import strategy_playbook

    action, detail = strategy_playbook(
        bearing="EXIT_REVIEW",
        source="momentum_role",
        short_weak=True,
        vol_flag=False,
        weak_streak=5,
        exit_streak_n=5,
    )
    assert action == "청산·교체 검토"
    assert "추가매수 금지" in detail
