"""Korean display helpers for journal / discretionary warnings."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.ko_display import (
    action_kind_ko,
    format_discretionary_warning,
    format_ineligibility_reason,
    reason_ko,
    subject_ko,
)


def test_reason_ko_known_phrases() -> None:
    assert "매크로" in reason_ko("macro shock — cut risk before window rule fires")
    assert "유동성" in reason_ko("liquidity event")
    assert "테스트" in reason_ko("test deviation")


def test_format_discretionary_warning_has_action_hint() -> None:
    e = SimpleNamespace(
        recorded_at="2026-07-16T12:00:00+00:00",
        subject="E",
        discretionary_reason="macro shock — cut risk before window rule fires",
        rationale="",
    )
    text = format_discretionary_warning(e)
    assert "2026-07-16" in text
    assert "재량 이탈" in text
    assert "할 일" in text
    assert "자동매매" in text


def test_action_kind_and_subject() -> None:
    assert action_kind_ko("WARN_DISCRETIONARY") == "재량 이탈 경고"
    assert action_kind_ko("QUAL_GATE") == "신평·공공 게이트"
    assert action_kind_ko("KILLSWITCH_WATCH") == "공식 출처 탐색"
    assert action_kind_ko("OPENDART_WATCH") == "제안 종목 OpenDART"
    assert "종목" in subject_ko("005930")
    assert "이벤트" in subject_ko("E")


def test_format_ineligibility_reason_quality_floor() -> None:
    assert format_ineligibility_reason(
        "품질 하한 미달: score_q=50.83 < 55"
    ) == "품질 하한 미달 (Q 50.8 < 55)"
    assert format_ineligibility_reason("품질 재료 없음 — 판정 불가") == (
        "품질 재료 없음 — 판정 불가"
    )
