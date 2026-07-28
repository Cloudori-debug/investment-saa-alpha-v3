"""CECS AI research markdown parser (request writing moved to weekly_qual_report)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

USAGE_WARNING = (
    "사실 조사 보조용입니다. 최종 점수·근거(rationale)는 출처 원문을 확인한 뒤 "
    "반드시 본인이 직접 작성하세요. AI 서술의 복사·붙여넣기는 채점 목적에 어긋납니다"
)


@dataclass(frozen=True)
class CecsResearchSubject:
    ticker: str
    name: str
    sector: str


@dataclass(frozen=True)
class ParsedResearchAxis:
    score_100: float
    rationale: str
    sources: tuple[str, ...]
    # True when AI left the score blank and the parser filled a neutral 50.
    provisional: bool = False


@dataclass(frozen=True)
class ParsedResearchSuggestion:
    ticker: str
    name: str
    execution: ParsedResearchAxis
    pension: ParsedResearchAxis
    purpose: ParsedResearchAxis


@dataclass(frozen=True)
class BatchParseResult:
    suggestions: tuple[ParsedResearchSuggestion, ...]
    failures: tuple[str, ...]


def parse_cecs_ai_research_markdown(markdown: str) -> BatchParseResult:
    """Parse the fixed batch schema; keep failures isolated per ticker."""
    header = re.compile(r"(?m)^## \[([^\]]+)\]\s+(.+?)\s*$")
    matches = list(header.finditer(markdown))
    if not matches:
        return BatchParseResult(
            suggestions=(),
            failures=("종목 블록(`## [TICKER] 종목명`)을 찾을 수 없습니다.",),
        )

    suggestions: list[ParsedResearchSuggestion] = []
    failures: list[str] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        ticker = _ticker(match.group(1))
        name = match.group(2).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[match.end() : end]
        if ticker in seen:
            failures.append(f"{ticker}: 중복 종목 블록")
            continue
        seen.add(ticker)
        try:
            axes = {
                axis: _parse_axis(block, axis)
                for axis in ("execution", "pension", "purpose")
            }
            suggestions.append(
                ParsedResearchSuggestion(
                    ticker=ticker,
                    name=name,
                    execution=axes["execution"],
                    pension=axes["pension"],
                    purpose=axes["purpose"],
                )
            )
        except ValueError as exc:
            failures.append(f"{ticker}: {exc}")
    return BatchParseResult(
        suggestions=tuple(suggestions),
        failures=tuple(failures),
    )


def _parse_axis(block: str, axis: str) -> ParsedResearchAxis:
    section_match = re.search(
        rf"(?ms)^### {re.escape(axis)}\s*$\n(.*?)(?=^### |\Z)",
        block,
    )
    if not section_match:
        raise ValueError(f"`### {axis}` 섹션 누락")
    section = section_match.group(1)
    score_match = re.search(
        r"(?m)^- 점수 제안\(0-100\):\s*(.+?)\s*$",
        section,
    )
    if not score_match:
        raise ValueError(f"{axis} 점수 필드 누락")
    score_text = score_match.group(1).strip()

    rationale_match = re.search(
        r"(?ms)^- 근거:\s*(.*?)(?=^- 출처:)",
        section,
    )
    if not rationale_match:
        raise ValueError(f"{axis} 근거 필드 누락")
    rationale = " ".join(
        line.strip()
        for line in rationale_match.group(1).strip().splitlines()
        if line.strip()
    )
    if not rationale or set(rationale) <= {"_"}:
        raise ValueError(f"{axis} 근거 미작성")
    unverifiable = _is_unverifiable(rationale)

    provisional = False
    if not score_text or set(score_text) <= {"_"}:
        # Blank score → provisional 50 (AI left score for human). Must stay labeled.
        score = 50.0
        provisional = True
    else:
        try:
            score = float(score_text)
        except ValueError as exc:
            raise ValueError(f"{axis} 점수가 숫자가 아님: {score_text}") from exc
        if not 0.0 <= score <= 100.0:
            raise ValueError(f"{axis} 점수 범위 이탈: {score}")

    source_match = re.search(r"(?ms)^- 출처:\s*(.*)$", section)
    if not source_match:
        raise ValueError(f"{axis} 출처 필드 누락")
    source_text = source_match.group(1).strip()
    sources = _parse_sources(source_text)
    if not sources:
        if unverifiable or _is_unverifiable(source_text):
            sources = ("확인 불가",)
        else:
            raise ValueError(f"{axis} 유효한 http(s) 출처 링크 없음")
    return ParsedResearchAxis(
        score_100=score,
        rationale=rationale,
        sources=sources,
        provisional=provisional,
    )


def _parse_sources(source_text: str) -> tuple[str, ...]:
    """Accept markdown links and bare http(s) URLs (common AI fill style)."""
    md_links = tuple(
        f"[{label.strip()}]({url.strip()})"
        for label, url in re.findall(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            source_text,
        )
    )
    if md_links:
        return md_links
    bare = re.findall(r"(?m)https?://[^\s\)\]\>\"']+", source_text)
    if bare:
        cleaned: list[str] = []
        seen: set[str] = set()
        for url in bare:
            url = url.rstrip(".,;)")
            if url in seen:
                continue
            seen.add(url)
            cleaned.append(url)
        return tuple(cleaned)
    return ()


def _is_unverifiable(text: str) -> bool:
    return "확인 불가" in (text or "")


def _ticker(value: str) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() else text


__all__ = [
    "USAGE_WARNING",
    "CecsResearchSubject",
    "ParsedResearchAxis",
    "ParsedResearchSuggestion",
    "BatchParseResult",
    "parse_cecs_ai_research_markdown",
]
