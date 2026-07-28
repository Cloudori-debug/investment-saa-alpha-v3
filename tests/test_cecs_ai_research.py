"""CECS AI research markdown parser + import/approval path."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_system.journal import clear_entries, list_entries
from alpha_system.ui.services.cecs_ai_research import parse_cecs_ai_research_markdown
from alpha_system.ui.services.cecs_workbench import (
    approve_ai_suggestions,
    import_ai_suggestions,
)
from alpha_system.ui.services.journal_filters import categorize


def test_parser_isolates_bad_stock_and_converts_fixed_fields() -> None:
    parsed = parse_cecs_ai_research_markdown(
        _filled_block("005830", "DB손해보험", 80, 50, 100)
        + "\n"
        + _filled_block("021240", "코웨이", 120, 50, 50)
    )

    assert len(parsed.suggestions) == 1
    suggestion = parsed.suggestions[0]
    assert suggestion.ticker == "005830"
    assert suggestion.execution.score_100 == 80
    assert suggestion.execution.sources == (
        "[1차 출처: DART](https://dart.fss.or.kr/e1)",
    )
    assert parsed.failures == ("021240: execution 점수 범위 이탈: 120.0",)


def test_parser_accepts_unverifiable_blank_score_as_neutral_50() -> None:
    markdown = """## [036530] SNT홀딩스

### execution
- 점수 제안(0-100): 65
- 근거: 분기배당 확인
- 출처: [1차 출처: DART](https://dart.fss.or.kr/e1)

### pension
- 점수 제안(0-100): 50
- 근거: 보고 없음 중립
- 출처: [1차 출처: FnGuide](https://example.com/p)

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "SNT홀딩스 보유목적"
- 출처: (확인 불가)
"""
    parsed = parse_cecs_ai_research_markdown(markdown)
    assert parsed.failures == ()
    assert len(parsed.suggestions) == 1
    purpose = parsed.suggestions[0].purpose
    assert purpose.score_100 == 50.0
    assert purpose.sources == ("확인 불가",)
    assert purpose.provisional is True
    assert parsed.suggestions[0].execution.provisional is False
    assert parsed.suggestions[0].pension.provisional is False


def test_parser_accepts_blank_score_with_rationale_and_bare_urls() -> None:
    markdown = """## [006040] 동원산업

### execution
- 점수 제안(0-100): _____
- 근거: 자사주 소각과 배당 확대 확인
- 출처:
  - https://www.hankyung.com/article/202409124934i
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=543395

### pension
- 점수 제안(0-100): _____
- 근거: 확인 불가 (정확한 출처 URL 특정 못함) — 검색 키워드 제안: "동원산업 국민연금"
- 출처:
  - 확인 불가 (정확한 출처 URL 특정 못함)

### purpose
- 점수 제안(0-100): _____
- 근거: 지주회사 전환 목적 확인
- 출처:
  - http://www.newstheone.com/news/articleView.html?idxno=110264
"""
    parsed = parse_cecs_ai_research_markdown(markdown)
    assert parsed.failures == ()
    assert len(parsed.suggestions) == 1
    row = parsed.suggestions[0]
    assert row.execution.score_100 == 50.0
    assert row.execution.provisional is True
    assert row.execution.sources[0].startswith("https://www.hankyung.com/")
    assert row.pension.score_100 == 50.0
    assert row.pension.provisional is True
    assert row.pension.sources == ("확인 불가",)
    assert row.purpose.provisional is True
    assert row.purpose.sources[0].startswith("http://www.newstheone.com/")


def test_import_stays_ai_suggested_and_approval_requires_source_review(
    tmp_path: Path,
) -> None:
    clear_entries()
    path = _one_row_template(tmp_path / "cecs.csv")
    parsed = parse_cecs_ai_research_markdown(
        _filled_block("005830", "DB손해보험", 80, 50, 100)
    )
    imported = import_ai_suggestions(
        path=path,
        suggestions=parsed.suggestions,
        report_name="completed.md",
        as_of=date(2026, 7, 17),
        journal_path=tmp_path / "journal.jsonl",
    )

    assert imported.imported_tickers == ("005830",)
    row = pd.read_csv(path, dtype=str).iloc[0]
    assert row["status"] == "ai_suggested"
    assert row["execution_continuity"] == "0.80"
    assert "https://dart.fss.or.kr/e1" in row["execution_sources"]
    with pytest.raises(ValueError, match="출처 확인"):
        approve_ai_suggestions(
            path=path,
            tickers=["005830"],
            reviewed_tickers=[],
            approved_by="operator",
            as_of=date(2026, 7, 17),
        )

    approved = approve_ai_suggestions(
        path=path,
        tickers=["005830"],
        reviewed_tickers=["005830"],
        approved_by="operator",
        as_of=date(2026, 7, 17),
        journal_path=tmp_path / "journal.jsonl",
    )
    assert approved.approved_tickers == ("005830",)
    row = pd.read_csv(path, dtype=str).iloc[0]
    assert row["status"] == "final"
    assert "AI 제안 기반, 사용자 승인일 2026-07-17" in row["execution_rationale"]
    assert "https://dart.fss.or.kr/e1" in row["execution_rationale"]
    kinds = {entry.action_kind for entry in list_entries()}
    assert "CECS_BATCH_IMPORT" in kinds
    assert "CECS_SCORE_APPROVED" in kinds
    assert categorize("CECS_BATCH_IMPORT") == "데이터"
    assert categorize("CECS_SCORE_APPROVED") == "입력"
    clear_entries()


def _filled_block(
    ticker: str,
    name: str,
    execution: int,
    pension: int,
    purpose: int,
) -> str:
    sections = []
    for axis, score, suffix in (
        ("execution", execution, "e1"),
        ("pension", pension, "p1"),
        ("purpose", purpose, "u1"),
    ):
        sections.append(
            f"""### {axis}
- 점수 제안(0-100): {score}
- 근거: [{axis[0].upper()}1] 확인 근거
- 출처: [1차 출처: DART](https://dart.fss.or.kr/{suffix})
"""
        )
    return f"## [{ticker}] {name}\n\n" + "\n".join(sections)


def _one_row_template(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "ticker": "005830",
                "name": "DB손해보험",
                "as_of": "2026-07-17",
                "sector": "insurance",
                "is_held": "False",
                "rank": "1",
                "execution_continuity": "",
                "execution_rationale": "",
                "pension_flow_score": "",
                "pension_rationale": "",
                "investment_purpose_flag": "",
                "investment_purpose_rationale": "",
                "policy_dependency_flag": "0.50",
                "policy_dependency_rationale": "",
                "cecs_computed": "",
                "scored_by": "",
                "scored_at": "",
                "status": "draft",
                "notes": "",
            }
        ]
    ).to_csv(path, index=False)
    return path
