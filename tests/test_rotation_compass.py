"""교체 나침반 unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.rotation_compass import (
    build_rotation_compass,
    BEARING_KO,
)


def _row(ticker: str, name: str, signal: str, step: str, weight: float = 5.0):
    return SimpleNamespace(
        ticker=ticker,
        name=name,
        weight_pct=weight,
        ops_signal=signal,
        ops_signal_label={"exit_full": "전량", "trim": "줄이기", "cash_half": "환금", "hold": "유지", "missing": "목표없음"}.get(signal, signal),
        ops_signal_detail=f"step {step}",
        extra={"ops_step_id": step},
    )


def test_evidence_lines_include_step() -> None:
    from alpha_system.ui.services.rotation_compass import evidence_lines_for_row

    row = SimpleNamespace(
        ticker="030200",
        name="KT",
        ops_signal="exit_full",
        ops_signal_label="전량",
        ops_signal_detail="제안 탈락 · 잔여 전량 환금 · 로테이션",
        ops_trim_pct=100,
        weight_pct=5.0,
        avg_price=45000.0,
        current_price=48000.0,
        remaining_upside_pct=None,
        target_detail="",
        extra={"ops_step_id": "S2a", "ops_rationale": "030200: not in proposal_book"},
    )
    lines = evidence_lines_for_row(row, in_proposal=False)
    blob = "\n".join(lines)
    assert "S2a" in blob
    assert "제안 북: 미포함" in blob
    assert "전량" in blob


def test_compass_hold_when_all_hold() -> None:
    c = build_rotation_compass(
        [_row("005830", "DB손보", "hold", "HOLD"), _row("021240", "코웨이", "hold", "HOLD")]
    )
    assert c.bearing == "hold"
    assert c.title_ko == "유지"
    assert c.replace_count == 0


def test_compass_replace_on_s2a() -> None:
    c = build_rotation_compass(
        [
            _row("005830", "DB손보", "hold", "HOLD"),
            _row("030200", "KT", "exit_full", "S2a"),
        ]
    )
    assert c.bearing == "replace"
    assert c.replace_count == 1
    assert "전량" in c.title_ko or c.title_ko == BEARING_KO["replace"]


def test_compass_cash_over_trim() -> None:
    c = build_rotation_compass(
        [
            _row("021240", "코웨이", "trim", "Sprox"),
            _row("005830", "DB손보", "cash_half", "S1"),
        ]
    )
    assert c.bearing == "cash"


def test_compass_empty() -> None:
    c = build_rotation_compass([])
    assert c.bearing == "hold"
    assert c.items == ()
