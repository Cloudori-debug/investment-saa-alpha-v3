"""L1 trail Review — T1/T2/T3 · L0 merge · no target write."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.ops_exit_signal import OpsExitSignal, apply_ops_exit_signals
from alpha_system.ui.services.trail_exit_signal import (
    T1,
    T2,
    T3,
    classify_trail_exit,
    merge_l0_l1,
    peak_drawdown,
    trail_from_snapshot,
)


def test_thresholds_approved() -> None:
    assert T1 == 0.12
    assert T2 == 0.20
    assert T3 == 0.28


def test_peak_drawdown() -> None:
    peak, dd = peak_drawdown([100, 120, 110], 96)
    assert peak == 120
    assert abs(dd - 0.2) < 1e-9


def test_t1_trim() -> None:
    # 12% dd from 100
    sig = classify_trail_exit(highs=[100], closes=[88], last=88, use_channel=False)
    assert sig.kind == "trim"
    assert sig.trim_pct == 25
    assert "트레일줄이기" in sig.label


def test_t2_half() -> None:
    sig = classify_trail_exit(highs=[100], closes=[80], last=80, use_channel=False)
    assert sig.kind == "cash_half"
    assert sig.trim_pct == 50


def test_t3_full() -> None:
    sig = classify_trail_exit(highs=[100], closes=[72], last=72, use_channel=False)
    assert sig.kind == "exit_full"
    assert sig.trim_pct == 100


def test_channel_break_exit() -> None:
    closes = [100.0] * 60 + [50.0]
    sig = classify_trail_exit(highs=[100], closes=closes, last=50.0)
    assert sig.channel_break is True
    assert sig.kind == "exit_full"
    assert "채널" in sig.label or "전량" in sig.label


def test_snapshot_high_52w_alone_does_not_fire() -> None:
    """52주 고점 단독 peak는 스펙 위반 · L1 미발화."""
    assert trail_from_snapshot(close=72, high_52w=100) is None


def test_snapshot_with_high_series_fires() -> None:
    sig = trail_from_snapshot(close=72, highs=[100, 95, 90], closes=[100, 95, 90, 72])
    assert sig is not None
    assert sig.kind == "exit_full"
    assert abs(sig.drawdown - 0.28) < 1e-9


def test_merge_l0_exit_beats_l1() -> None:
    l0 = OpsExitSignal(
        kind="exit_full",
        label="전량",
        detail="논지",
        trim_pct=100,
        step_id="S0",
        rationale="thesis",
    )
    l1 = classify_trail_exit(highs=[100], closes=[88], last=88, use_channel=False)
    merged = merge_l0_l1(l0, l1)
    assert merged.step_id == "S0"
    assert merged.kind == "exit_full"


def test_merge_l1_stronger_than_hold() -> None:
    l0 = OpsExitSignal(
        kind="hold",
        label="유지",
        detail="미근접",
        step_id="HOLD",
        rationale="hold",
    )
    l1 = classify_trail_exit(highs=[100], closes=[80], last=80, use_channel=False)
    merged = merge_l0_l1(l0, l1)
    assert merged.kind == "cash_half"
    assert merged.step_id == "L1"
    assert "트레일" in merged.label


def test_apply_ops_high_52w_snapshot_does_not_force_sell(tmp_path) -> None:
    """스냅샷 high_52w만으로는 오늘 비중 전량 매도가 되면 안 됨."""
    row = SimpleNamespace(
        ticker="005930",
        current_price=80.0,
        current_pbr=None,
        remaining_upside_pct=30.0,
        extra={},
        ops_signal=None,
        ops_signal_label=None,
        ops_signal_detail=None,
        ops_trim_pct=None,
    )
    apply_ops_exit_signals(
        [row],
        proposal_tickers={"005930"},
        fundamentals_by_ticker={},
        exit_tickers={
            "005930": {"target_price": 200.0},
        },
        defaults={"trail": {"t1": 0.12, "t2": 0.20, "t3": 0.28}},
        check_proposal_membership=False,
        trail_by_ticker={"005930": (80.0, 100.0)},  # close, high_52w
        apply_trail=True,
    )
    # L0 hold (목표 미근접) · L1 미발화
    assert row.ops_signal == "hold"
    assert row.extra.get("trail_kind") in {None, "hold"}
    assert not (tmp_path / "target_portfolio.csv").exists()
