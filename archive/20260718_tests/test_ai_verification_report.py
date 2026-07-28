"""AI verification report builder."""

from __future__ import annotations

from datetime import datetime

from alpha_system.journal import clear_entries, list_entries
from alpha_system.ui.services.ai_verification_report import (
    build_ai_verification_markdown,
    write_ai_verification_report,
)
from alpha_system.ui.services.context import load_context
from alpha_system.ui.services.journal_filters import categorize
from alpha_system.ui.services.ui_copy import load_ui_copy


def test_ai_verification_markdown_has_required_sections(tmp_path) -> None:
    load_ui_copy.cache_clear()
    clear_entries()
    ctx = load_context()
    md = build_ai_verification_markdown(ctx, generated_at=datetime(2026, 7, 16, 12, 0, 0))
    assert "# AI 검증 리포트" in md
    assert "PRE_LAUNCH" in md or "가동" in md
    assert "commercial_code_enforcement_decrees" in md
    assert "관보" in md
    assert "워치리스트" in md
    assert "금융위원회" in md or "회계기준원" in md
    assert "논지 훼손" in md
    assert "1차 출처" in md
    assert "확인 불가" in md
    assert "미확정 보도 단계" in md
    assert "참고용" in md


def test_ai_verification_writes_file_and_journals(tmp_path) -> None:
    load_ui_copy.cache_clear()
    clear_entries()
    ctx = load_context()
    report = write_ai_verification_report(
        ctx,
        docs_dir=tmp_path,
        generated_at=datetime(2026, 7, 16, 15, 30, 0),
        journal=True,
    )
    assert report.path.exists()
    assert report.path.name == "ai_verification_report_20260716.md"
    assert "AI 검증 리포트" in report.path.read_text(encoding="utf-8")
    kinds = [e.action_kind for e in list_entries()]
    assert "AI_VERIFICATION_REPORT" in kinds
    assert categorize("AI_VERIFICATION_REPORT") == "데이터"
    clear_entries()
