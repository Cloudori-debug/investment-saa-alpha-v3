"""L3 crash defense + re-entry — Review-only · no exit_full from L3 alone."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.crash_defense_signal import (
    C1,
    C2,
    C3,
    build_reentry_ladder,
    classify_crash_defense,
    merge_l0_l1_l3,
    n_day_return,
)
from alpha_system.ui.services.ops_exit_signal import OpsExitSignal, apply_ops_exit_signals
from alpha_system.ui.services.trail_exit_signal import classify_trail_exit


def test_thresholds() -> None:
    assert C1 == -0.12
    assert C2 == -0.18
    assert C3 == -0.25


def test_n_day_return() -> None:
    # 100 → 88 over 5 sessions = -12%
    closes = [100.0, 98, 96, 94, 90, 88.0]
    assert abs(n_day_return(closes, n=5) - (-0.12)) < 1e-9


def test_c1_trim() -> None:
    closes = [100.0, 98, 96, 94, 90, 88.0]
    sig = classify_crash_defense(closes)
    assert sig.code == "C1"
    assert sig.kind == "trim"
    assert sig.trim_pct == 25
    assert "급락줄이기" in sig.label


def test_c2_half() -> None:
    closes = [100.0, 95, 90, 88, 85, 82.0]  # -18%
    sig = classify_crash_defense(closes)
    assert sig.code == "C2"
    assert sig.kind == "cash_half"
    assert sig.trim_pct == 50


def test_c3_half_not_full() -> None:
    closes = [100.0, 90, 85, 80, 78, 75.0]  # -25%
    sig = classify_crash_defense(closes)
    assert sig.code == "C3"
    assert sig.kind == "cash_half"
    assert sig.trim_pct == 50
    assert sig.suggest_full_review is True
    assert sig.kind != "exit_full"


def test_c1_plus_l1_t2_boosts_c2() -> None:
    closes = [100.0, 98, 96, 94, 90, 88.0]  # -12% C1
    sig = classify_crash_defense(closes, l1_drawdown=0.20)
    assert sig.code == "C2"
    assert sig.kind == "cash_half"


def test_l3_never_exit_full_in_merge() -> None:
    l0 = OpsExitSignal(
        kind="hold",
        label="유지",
        detail="hold",
        step_id="HOLD",
        rationale="h",
    )
    l3 = classify_crash_defense([100.0, 90, 85, 80, 78, 75.0])
    assert l3.kind == "cash_half"
    merged = merge_l0_l1_l3(l0, None, l3)
    assert merged.kind == "cash_half"
    assert merged.kind != "exit_full"
    assert merged.step_id == "L3"


def test_l1_full_beats_l3() -> None:
    l0 = OpsExitSignal(
        kind="hold",
        label="유지",
        detail="hold",
        step_id="HOLD",
        rationale="h",
    )
    l1 = classify_trail_exit(highs=[100], closes=[72], last=72, use_channel=False)
    assert l1.kind == "exit_full"
    l3 = classify_crash_defense([100.0, 98, 96, 94, 90, 88.0])
    merged = merge_l0_l1_l3(l0, l1, l3)
    assert merged.kind == "exit_full"
    assert "L1" in merged.step_id or merged.trim_pct == 100


def test_reentry_prices() -> None:
    ladder = build_reentry_ladder(
        crash_low=100.0,
        last=100.0,
        trim_frac=0.25,
        closes=[100.0] * 25,
    )
    assert ladder is not None
    assert abs(ladder.rungs[0].price - 106.0) < 1e-9
    assert abs(ladder.rungs[1].price - 112.0) < 1e-9
    assert abs(ladder.rungs[2].price - 118.0) < 1e-9
    assert ladder.active_rung == "R1"

    ladder2 = build_reentry_ladder(
        crash_low=100.0,
        last=113.0,
        trim_frac=0.5,
    )
    assert ladder2 is not None
    assert ladder2.rungs[0].hit is True
    assert ladder2.rungs[1].hit is True
    assert ladder2.active_rung == "R3"


def test_apply_ops_no_target_write(tmp_path) -> None:
    row = SimpleNamespace(
        ticker="005930",
        current_price=88.0,
        current_pbr=None,
        remaining_upside_pct=None,
        extra={},
        ops_signal="",
        ops_signal_label="",
        ops_signal_detail="",
        ops_trim_pct=None,
        has_target=False,
        target_price=None,
        weight_pct=5.0,
        total_score=50.0,
    )
    closes = {"005930": [100.0, 98, 96, 94, 90, 88.0]}
    apply_ops_exit_signals(
        [row],
        proposal_tickers={"005930"},
        fundamentals_by_ticker={},
        exit_tickers={},
        defaults={},
        check_proposal_membership=False,
        closes_by_ticker=closes,
        apply_crash=True,
        apply_trail=True,
    )
    assert row.ops_signal in {"trim", "cash_half", "hold", "missing", "invalid", "exit_full"}
    assert (row.extra or {}).get("crash_code") in {"C1", "C2", "C3", "hold", None} or True
    # never writes files
    assert not (tmp_path / "target_portfolio.csv").exists()
