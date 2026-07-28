"""Momentum Holding Monitor — bearing rules & streak."""

from __future__ import annotations

from alpha_system.ui.services.momentum_holding_monitor import (
    classify_bearing,
    _weak_streak_from_history,
)


def test_bearing_enter_ok() -> None:
    b, _ = classify_bearing(
        ts_sign="UP",
        xs_pct=70,
        vol_flag=False,
        grade="GO",
        weak_streak=0,
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


def test_weak_streak_counts_prior_days() -> None:
    hist = [
        {"as_of": "2026-07-25", "weak": True},
        {"as_of": "2026-07-26", "weak": True},
        {"as_of": "2026-07-27", "weak": True},
    ]
    assert _weak_streak_from_history(hist, today_weak=True, today="2026-07-28") == 4
    assert _weak_streak_from_history(hist, today_weak=False, today="2026-07-28") == 0
