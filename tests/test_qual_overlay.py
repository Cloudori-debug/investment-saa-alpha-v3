"""Qual overlay — gates and ±K swaps without changing total_score."""

from __future__ import annotations

import pytest

from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import select_eligible
from alpha_system.sizing.qual_overlay import (
    QualGate,
    QualOverlay,
    QualSwap,
    add_gate,
    apply_qual_overlay,
    overlay_from_dict,
    require_source_url,
)
from alpha_system.ui.services.rank_watchboard import TONE_ELIGIBLE, watch_preview_tone


def _score(ticker: str, weight: float, *, sector: str = "misc") -> NameScore:
    return NameScore(
        ticker=ticker,
        name=ticker,
        factors={},
        total_score=weight,
        eligibility=True,
        weight_input=weight,
        eligibility_reason="test",
        sector=sector,
    )


def test_gate_drops_name_next_eligible_fills() -> None:
    scores = [_score(str(i).zfill(6), 100 - i, sector=f"s{i}") for i in range(1, 8)]
    overlay = QualOverlay(
        gates=(
            QualGate(
                ticker="000001",
                reason="downgrade",
                source_url="https://example.test/rating",
            ),
        )
    )
    reasons: dict[str, str] = {}
    selected, warnings = select_eligible(
        scores,
        target_names=3,
        max_names_per_sector=2,
        overlay=overlay,
        skip_reasons=reasons,
    )
    assert [s.ticker for s in selected] == ["000002", "000003", "000004"]
    assert any("000001" in w for w in warnings)
    assert reasons.get("000001") == "정성 게이트"


def test_swap_within_two_slots_changes_book() -> None:
    scores = [
        _score("000001", 90, sector="a"),
        _score("000002", 80, sector="b"),
        _score("000003", 70, sector="c"),
        _score("000004", 60, sector="d"),
    ]
    overlay = QualOverlay(
        max_swap_slots=2,
        swaps=(
            QualSwap(
                promote="000004",
                demote="000002",
                source_url="https://example.test/nps",
            ),
        ),
    )
    selected, warnings = select_eligible(
        scores, target_names=3, max_names_per_sector=2, overlay=overlay
    )
    assert [s.ticker for s in selected] == ["000001", "000004", "000003"]
    assert any("qual swap" in w for w in warnings)


def test_swap_beyond_max_slots_is_skipped() -> None:
    passed = [
        _score("000001", 90),
        _score("000002", 80),
        _score("000003", 70),
        _score("000004", 60),
    ]
    overlay = QualOverlay(
        max_swap_slots=2,
        swaps=(
            QualSwap(
                promote="000004",
                demote="000001",
                source_url="https://example.test/too-far",
            ),
        ),
    )
    ordered, warnings = apply_qual_overlay(passed, overlay)
    assert [s.ticker for s in ordered] == ["000001", "000002", "000003", "000004"]
    assert any("max 2" in w for w in warnings)


def test_overlay_does_not_change_scores() -> None:
    row = _score("000001", 61.36)
    overlay = QualOverlay(
        gates=(
            QualGate(
                ticker="000001",
                reason="negative_watch",
                source_url="https://example.test/watch",
            ),
        )
    )
    kept, _ = apply_qual_overlay([row], overlay)
    assert kept == []
    assert row.total_score == 61.36
    assert row.weight_input == 61.36


def test_control_purpose_is_valid_gate_reason() -> None:
    overlay = QualOverlay()
    updated = add_gate(
        overlay,
        ticker="005930",
        reason="control_purpose",
        source_url="https://opendart.fss.or.kr/",
    )
    assert updated.active_gates()[0].reason == "control_purpose"


def test_add_gate_requires_http_url() -> None:
    overlay = QualOverlay()
    with pytest.raises(ValueError, match="출처 URL"):
        add_gate(
            overlay,
            ticker="005830",
            reason="downgrade",
            source_url="dart-only",
        )
    require_source_url("https://dart.fss.or.kr/x")
    updated = add_gate(
        overlay,
        ticker="005830",
        reason="downgrade",
        source_url="https://dart.fss.or.kr/x",
    )
    assert updated.active_gates()[0].ticker == "005830"


def test_apply_opendart_flag_gates_adds_kinds_without_mixing_scores() -> None:
    from types import SimpleNamespace

    from alpha_system.sizing.qual_overlay import apply_opendart_flag_gates

    overlay = QualOverlay(
        gates=(
            QualGate(
                ticker="005930",
                reason="downgrade",
                source_url="https://example.test/rating",
            ),
        )
    )
    flags = [
        SimpleNamespace(
            ticker="005930",
            kind="control_purpose",
            source_url="https://opendart.fss.or.kr/a",
            note="경영참여",
        ),
        SimpleNamespace(
            ticker="005930",
            kind="pension_exit",
            source_url="https://opendart.fss.or.kr/b",
            note="연기금",
        ),
        SimpleNamespace(
            ticker="000660",
            kind="downgrade",
            source_url="https://opendart.fss.or.kr/c",
            note="ignored",
        ),
    ]
    updated, applied = apply_opendart_flag_gates(
        overlay, flags, as_of="2026-08-31"
    )
    assert applied == ("005930",)
    reasons = {g.reason for g in updated.active_gates() if g.ticker == "005930"}
    assert reasons == {"downgrade", "control_purpose", "pension_exit"}
    again, applied2 = apply_opendart_flag_gates(updated, flags, as_of="2026-08-31")
    assert applied2 == ()
    assert again.active_gates() == updated.active_gates()
    row = _score("005930", 70.0)
    kept, _ = apply_qual_overlay([row], updated)
    assert kept == []
    assert row.total_score == 70.0


def test_gated_name_watch_tone_is_eligible_not_proposal() -> None:
    assert (
        watch_preview_tone(
            score=90,
            cutoff=70,
            eligible_rank=1,
            target_n=6,
            in_proposal=False,
        )
        == TONE_ELIGIBLE
    )


def test_overlay_from_dict_ignores_unknown_reason() -> None:
    overlay = overlay_from_dict(
        {
            "gates": [
                {
                    "ticker": "1",
                    "reason": "broker_tp",
                    "source_url": "https://x.test",
                },
                {
                    "ticker": "005830",
                    "reason": "pension_exit",
                    "source_url": "https://dart.fss.or.kr/y",
                },
            ]
        }
    )
    assert [g.ticker for g in overlay.active_gates()] == ["005830"]
    assert overlay.active_gates()[0].reason == "pension_exit"
