"""CECS batch research request and fixed-schema markdown parser."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from alpha_system.journal import append_record

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
class CecsAiResearchReport:
    markdown: str
    path: Path
    generated_at: datetime
    tickers: tuple[str, ...]
    mode: str
    provider_status: str


@dataclass(frozen=True)
class ParsedResearchAxis:
    score_100: float
    rationale: str
    sources: tuple[str, ...]


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


def write_cecs_ai_research_report(
    *,
    subjects: Sequence[CecsResearchSubject],
    docs_dir: Path,
    generated_at: datetime | None = None,
    journal_path: Path | None = None,
) -> CecsAiResearchReport:
    if not subjects:
        raise ValueError("AI 조사 리포트 대상 종목이 없습니다.")
    generated_at = generated_at or datetime.now()
    normalized = tuple(
        CecsResearchSubject(
            ticker=_ticker(subject.ticker),
            name=subject.name.strip(),
            sector=subject.sector.strip(),
        )
        for subject in subjects
    )
    mode = "batch"
    path = docs_dir / f"cecs_ai_research_batch_{generated_at.strftime('%Y%m%d')}.md"
    markdown = build_cecs_ai_research_markdown(
        normalized,
        generated_at=generated_at,
    )
    docs_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, markdown)

    append_record(
        action_kind="CECS_AI_RESEARCH_GENERATED",
        as_of=generated_at.date(),
        subject="batch",
        rationale=(
            f"CECS batch AI research request generated: {path.name}"
        ),
        payload={
            "path": str(path),
            "tickers": [subject.ticker for subject in normalized],
            "mode": mode,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "provider_status": "EXTERNAL_FILL_REQUIRED",
        },
        journal_path=journal_path,
    )
    return CecsAiResearchReport(
        markdown=markdown,
        path=path,
        generated_at=generated_at,
        tickers=tuple(subject.ticker for subject in normalized),
        mode=mode,
        provider_status="EXTERNAL_FILL_REQUIRED",
    )


def build_cecs_ai_research_markdown(
    subjects: Sequence[CecsResearchSubject],
    *,
    generated_at: datetime,
) -> str:
    """Build a fixed-schema request for an external web-search-capable AI."""
    lines = [
        "# CECS AI 조사 리포트",
        "",
        f"- 생성일시: `{generated_at.isoformat(timespec='seconds')}`",
        f"- 대상: **{len(subjects)}종**",
        "- 상태: **외부 AI 작성 대기**",
        "",
        f"> ⚠️ {USAGE_WARNING}",
        "",
        "## AI 답변 규칙",
        "",
        "1. execution / pension / purpose마다 점수 제안(0~100)·근거·출처를 모두 작성한다.",
        "2. 사용한 링크를 전부 출처 필드에 나열하고 근거 문장에 `[E1]` 같은 표식을 붙여 대응시킨다.",
        "3. 출처 설명 앞에 `1차 출처:` 또는 `보도:`를 붙여 구분한다.",
        "4. 뉴스와 1차 출처가 다르면 둘 다 쓰되 공시·IR·관보 원문을 우선한다.",
        "5. 확인 불가는 추정하지 않는다. 근거에 `확인 불가; 검색 키워드: ...`를 쓰고, "
        "점수는 `50`(중립) 또는 빈칸(`_____`)으로 둔다. 출처는 `(확인 불가)`로 둬도 된다. "
        "빈칸 점수는 업로드 시 내부 0.50으로 변환된다.",
        "6. 제목(`## [TICKER]`)과 3개 축 제목·필드명은 파서 계약이므로 바꾸지 않는다.",
        "7. `점수 제안(0-100):` 뒤에는 **숫자만** 쓴다. 예: `65`. "
        "`65 (AI 초안)`, `65점`, `확인 불가`를 점수 칸에 붙이면 업로드 파서가 거부한다.",
        "",
        "## 사용 방법",
        "",
        "외부 AI 도구(웹검색 가능)에 이 파일을 붙여넣어 빈칸을 채운 뒤 "
        "완성된 마크다운 파일을 CECS 채점 화면에 업로드하세요.",
        "",
    ]
    for index, subject in enumerate(subjects, 1):
        lines.extend(_subject_section(index, subject))
    lines.extend(
        [
            "---",
            "",
            "업로드 결과는 `ai_suggested` 초안이며 출처 확인·사용자 승인 전에는 final이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)


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

    if not score_text or set(score_text) <= {"_"}:
        # Blank score → provisional 50 when facts exist (AI may leave score for human).
        # Unverifiable blanks also map to neutral 50.
        score = 50.0
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


def _subject_section(index: int, subject: CecsResearchSubject) -> list[str]:
    name = subject.name or subject.ticker
    basic = [
        f"## [{subject.ticker}] {name}",
        "",
        f"- 업종: {subject.sector or '확인 불가'}",
        "",
    ]
    return (
        basic
        + _research_block(
            title="execution",
            hint=(
                "최근 4개 분기 환원 이벤트(배당·자사주 매입/소각), 날짜·규모. "
                "환원 형태 동일 척도, 같은 분기 복수 이벤트는 1회."
            ),
        )
        + _research_block(
            title="pension",
            hint=(
                "연기금 보유·최근 지분 변동. 미보유·보고 없음은 내부 0.5="
                "외부 점수 50 규칙 적용 여부 명시."
            ),
        )
        + _research_block(
            title="purpose",
            hint=(
                "최근 주주환원 관련 공시·IR 요지와 투자목적. 일반·단순투자=100, "
                "경영참여=30, 보고 없음=50."
            ),
        )
    )


def _research_block(
    *,
    title: str,
    hint: str,
) -> list[str]:
    return [
        f"### {title}",
        "",
        f"<!-- 조사 힌트: {hint} -->",
        "- 점수 제안(0-100): _____",
        "- 근거: _____",
        "- 출처: [1차 출처: 설명](URL), [보도: 설명](URL)",
        "",
    ]


def _atomic_write_text(path: Path, content: str) -> None:
    handle, raw = tempfile.mkstemp(
        prefix=f".{path.stem}_",
        suffix=path.suffix,
        dir=path.parent,
    )
    os.close(handle)
    temp = Path(raw)
    try:
        temp.write_text(content, encoding="utf-8")
        if temp.stat().st_size < 100:
            raise ValueError("AI 조사 리포트 임시 파일이 비정상적으로 작습니다.")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _ticker(value: str) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() else text
