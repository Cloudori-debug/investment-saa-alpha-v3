"""Korean display helpers for journal / discretionary warnings."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.ko_display import (
    action_kind_ko,
    format_discretionary_warning,
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
    assert "종목" in subject_ko("005930")
    assert "이벤트" in subject_ko("E")
