"""Step exit cues: 유지 / 줄이기 / 환금(절반) / 전량."""

from __future__ import annotations

from datetime import date, timedelta

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.ops_exit_signal import (
    actionable_ops_signals,
    apply_ops_exit_signals,
    classify_ops_exit_signal,
)


def test_thesis_is_full_exit() -> None:
    sig = classify_ops_exit_signal(
        "005830",
        fundamentals={"pbr": 1.5},
        prices={"current_price": 200000},
        ticker_targets={"valuation": {"pbr_max": 1.4}, "target_price": 218000},
        in_proposal=True,
        thesis_flags={"thesis_broken": True},
    )
    assert sig.kind == "exit_full"
    assert sig.label == "전량"
    assert sig.step_id == "S0"


def test_proposal_drop_is_full_exit() -> None:
    sig = classify_ops_exit_signal(
        "005830",
        fundamentals={"pbr": 0.9},
        prices={"current_price": 146800},
        ticker_targets={"valuation": {"pbr_max": 1.4}, "target_price": 218000},
        in_proposal=False,
    )
    assert sig.kind == "exit_full"
    assert sig.step_id == "S2a"
    assert "탈락" in sig.detail


def test_missing_target() -> None:
    sig = classify_ops_exit_signal(
        "192400",
        fundamentals={"pbr": 0.6},
        prices={"current_price": 10000},
        ticker_targets={},
        in_proposal=True,
    )
    assert sig.kind == "missing"
    assert sig.label == "목표없음"


def test_hold_below_proximity() -> None:
    sig = classify_ops_exit_signal(
        "030200",
        fundamentals={"pbr": 0.5},
        prices={"current_price": 40000},
        ticker_targets={"valuation": {"pbr_max": 0.86}, "target_price": 80000},
        in_proposal=True,
        remaining_upside_pct=100.0,
    )
    assert sig.kind == "hold"
    assert sig.label == "유지"


def test_pre_hit_quarter_step() -> None:
    sig = classify_ops_exit_signal(
        "021240",
        fundamentals={},
        prices={"current_price": 120000},
        ticker_targets={"target_price": 150000.0, "valuation": {}},
        in_proposal=True,
    )
    # 120/150 = 80% → 줄이기 25%
    assert sig.kind == "trim"
    assert sig.trim_pct == 25
    assert sig.label == "줄이기"


def test_target_hit_half_cash() -> None:
    sig = classify_ops_exit_signal(
        "105560",
        fundamentals={},
        prices={"current_price": 210000},
        ticker_targets={"target_price": 210000.0, "valuation": {}},
        in_proposal=True,
    )
    assert sig.kind == "cash_half"
    assert sig.label == "환금"
    assert sig.trim_pct == 50
    assert sig.step_id == "S1"


def test_time_cap_full_exit() -> None:
    old = (date.today() - timedelta(weeks=5)).isoformat()
    sig = classify_ops_exit_signal(
        "000270",
        fundamentals={},
        prices={"current_price": 250000},
        ticker_targets={
            "target_price": 240000.0,
            "valuation": {},
            "target_hit_as_of": old,
        },
        in_proposal=True,
        as_of=date.today(),
        time_cap_weeks=4,
    )
    assert sig.kind == "exit_full"
    assert sig.step_id == "S2c"


def test_time_cap_ignores_approved_as_of_alone() -> None:
    """Approving a target weeks ago must not skip S1 on first hit."""
    old = (date.today() - timedelta(weeks=8)).isoformat()
    sig = classify_ops_exit_signal(
        "000270",
        fundamentals={},
        prices={"current_price": 250000},
        ticker_targets={
            "target_price": 240000.0,
            "valuation": {},
            "approved_as_of": old,
        },
        in_proposal=True,
        as_of=date.today(),
        time_cap_weeks=4,
    )
    assert sig.kind == "cash_half"
    assert sig.step_id == "S1"


def test_apply_and_actionable() -> None:
    rows = [
        PortfolioRow(
            ticker="030200",
            name="KT",
            weight_pct=5.0,
            initial_weight_pct=None,
            avg_price=None,
            current_price=50000,
            target_price=90000,
            target_progress=None,
            remaining_upside_pct=80.0,
            has_target=True,
            target_detail="",
            cap_pct=35.0,
            cap_headroom_pct=30.0,
            cap_near=False,
            current_pbr=0.5,
            pbr_max=0.86,
        ),
        PortfolioRow(
            ticker="105560",
            name="KB",
            weight_pct=3.0,
            initial_weight_pct=None,
            avg_price=None,
            current_price=220000,
            target_price=210000,
            target_progress=None,
            remaining_upside_pct=-4.0,
            has_target=True,
            target_detail="",
            cap_pct=35.0,
            cap_headroom_pct=32.0,
            cap_near=False,
        ),
    ]
    apply_ops_exit_signals(
        rows,
        proposal_tickers={"030200", "105560"},
        fundamentals_by_ticker={"030200": {"pbr": 0.5}, "105560": {}},
        exit_tickers={
            "030200": {"valuation": {"pbr_max": 0.86}, "target_price": 90000},
            "105560": {"target_price": 210000.0, "valuation": {}},
        },
        defaults={"exit_time_cap_weeks": 4},
        check_proposal_membership=False,
    )
    assert rows[0].ops_signal == "hold"
    assert rows[1].ops_signal == "cash_half"
    assert rows[1].ops_signal_label == "환금"
    actionable = actionable_ops_signals(rows)
    assert len(actionable) == 1
    assert actionable[0].ticker == "105560"


def test_missing_price_is_invalid_not_hold() -> None:
    sig = classify_ops_exit_signal(
        "000660",
        fundamentals={},
        prices={},
        ticker_targets={"target_price": 4200000.0, "valuation": {}},
        in_proposal=True,
    )
    assert sig.kind == "invalid"
    assert sig.label == "데이터없음"
    assert "무효" in sig.detail
