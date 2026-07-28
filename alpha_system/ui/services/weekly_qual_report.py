"""Weekly integrated qualitative AI report — request schema A–E + parser.

Sections:
  A_CECS_SUMMARY — shortlist 30 CECS axis summaries
  B_FINAL6_DEEP — deep dive for proposed six
  C_T2_EVENTS — commercial code / MSCI / IFRS18
  D_THESIS — thesis damage signs
  E_TARGET_VALUATION — target PBR/price proposals for six

AI suggestions stay domain-isolated until separate approval gates apply them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.journal import append_record
from alpha_system.ui.services.cecs_ai_research import (
    USAGE_WARNING,
    CecsResearchSubject,
    ParsedResearchAxis,
    ParsedResearchSuggestion,
    parse_cecs_ai_research_markdown,
)

SECTION_IDS = (
    "A_CECS_SUMMARY",
    "B_FINAL6_DEEP",
    "C_T2_EVENTS",
    "D_THESIS",
    "E_TARGET_VALUATION",
)

DOMAIN_KEYS = ("cecs", "t2", "thesis", "targets")

# Separate suggestion stores so monthly CECS upload cannot wipe weekly C/D/E.
SUGGESTIONS_LANE_WEEKLY = "weekly"
SUGGESTIONS_LANE_MONTHLY = "monthly"
SUGGESTIONS_FILE_WEEKLY = "weekly_qual_suggestions.json"
SUGGESTIONS_FILE_MONTHLY = "monthly_cecs_suggestions.json"

WEEKLY_DOMAIN_KEYS = ("t2", "thesis", "targets")
MONTHLY_DOMAIN_KEYS = ("cecs",)


@dataclass(frozen=True)
class WeeklySubject:
    ticker: str
    name: str
    sector: str = ""


@dataclass(frozen=True)
class WeeklyQualReport:
    markdown: str
    path: Path
    report_id: str
    as_of: date
    generated_at: datetime
    input_snapshot_hash: str
    summary_tickers: tuple[str, ...]
    deep_tickers: tuple[str, ...]


@dataclass(frozen=True)
class ParsedT2Event:
    event_id: str
    fired: bool
    rationale: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ParsedThesis:
    damage: bool
    rationale: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ParsedTargetValuation:
    ticker: str
    name: str
    pbr_max: float | None
    target_price: float | None
    rationale: str
    sources: tuple[str, ...]
    fundamental_reason: str


@dataclass(frozen=True)
class ParsedDeepDive:
    ticker: str
    name: str
    disclosure: str
    buyback_dividend: str
    pension: str
    investment_purpose: str
    risks: str
    sources: tuple[str, ...]


@dataclass
class WeeklyParseResult:
    report_id: str
    as_of: str
    input_snapshot_hash: str
    cecs_suggestions: tuple[ParsedResearchSuggestion, ...] = ()
    deep_dives: tuple[ParsedDeepDive, ...] = ()
    t2_events: tuple[ParsedT2Event, ...] = ()
    thesis: ParsedThesis | None = None
    targets: tuple[ParsedTargetValuation, ...] = ()
    quant_signals: tuple[dict[str, str], ...] = ()
    domain_failures: dict[str, tuple[str, ...]] = field(default_factory=dict)
    domain_status: dict[str, str] = field(default_factory=dict)


def build_weekly_qual_markdown(
    *,
    summary_subjects: Sequence[WeeklySubject],
    deep_subjects: Sequence[WeeklySubject],
    t2_event_ids: Sequence[str],
    as_of: date,
    generated_at: datetime,
    report_id: str,
    input_snapshot_hash: str,
    existing_exit: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    lines = [
        "# 주간 통합 정성 AI 요청서",
        "",
        f"- report_id: `{report_id}`",
        f"- as_of: `{as_of.isoformat()}`",
        f"- generated_at: `{generated_at.isoformat(timespec='seconds')}`",
        f"- input_snapshot_hash: `{input_snapshot_hash}`",
        "",
        f"> {USAGE_WARNING}",
        "",
        "## 작성 규칙",
        "",
        "1. 섹션 헤더(`## A_CECS_SUMMARY` 등)와 필드 라벨을 변경하지 마세요.",
        "2. 확인 불가한 항목은 추정하지 말고 근거에 `확인 불가; 검색 키워드: ...`를 적으세요.",
        "3. 각 영역은 별도 승인됩니다. 한 섹션 실패가 다른 섹션을 자동 승인하지 않습니다.",
        "4. `target_portfolio.csv` 변경 제안은 금지입니다. 목표가 YAML 제안만 허용합니다.",
        "5. **채움 순서(필수):** `C_T2_EVENTS` → `D_THESIS` → `E_TARGET_VALUATION` → `A_CECS_SUMMARY`.",
        "   (선택) `B_FINAL6_DEEP` · `F_QUANT_EVENTS`는 C/D/E 이후.",
        "6. **출력:** 설명·서론 없이 **이 Markdown 전체**(빈칸만 채운 완성본). "
        "헤더 추가·삭제·번역 금지. as_of 기준(「오늘」금지).",
        "7. **숫자 칸 형식(파서 계약 — 반드시 준수)**",
        "   - CECS `점수 제안(0-100):` → **숫자만**. 예: `65`",
        "     금지: `65 (AI 초안)`, `65점`, `약 65`, 점수 칸에 `확인 불가`",
        "     못 정하면 `_____`만 (업로드 시 잠정 50). `확인 불가`는 근거·출처에만.",
        "   - 목표가 `pbr_max:` → **숫자만**. 예: `0.75`",
        "     금지: `0.75배`, `0.7배 (2028년 목표)`, `1.4배 (대신증권…)`",
        "   - 목표가 `target_price:` → **원 단위 숫자만** (쉼표·원·범위·주석 금지). 예: `48000`",
        "     금지: `48,000원`, `200,000~250,000원`, `150000원 (한화…)`",
        "   - `pbr_max`와 `target_price` 중 **최소 1개**는 숫자로 채우세요. 둘 다 `_____`면 업로드 실패.",
        "   - 증권사명·범위·근거 설명은 `펀더멘털 사유`/`근거` 칸에만 쓰세요.",
        "   - 출처 URL은 줄마다 단독으로 적어도 됩니다.",
        "8. **자기점검(출력 전):** C 근거≠`_____` · D 근거≠`_____` · "
        "E 전 TARGET 펀더멘털·근거·URL≥1 · A 점수=숫자|`_____`.",
        "9. 이 파일은 **조사 초안**입니다. 최종 점수·fired는 사람이 출처 원문 확인 후 승인합니다.",
        "",
        "### CECS 3축 채점표 (A — 이 표만 따를 것)",
        "",
        "**execution (주주환원 연속성)** — 최근 완결 4개 분기(배당·자사주 매입·소각).",
        "분기당 이벤트 1건 이상=그 분기 충족. 동일 분기 복수는 1회. "
        "연·반기 배당은 **결의/지급이 속한 분기만** 인정(프로그램 걸쳐 셈 금지).",
        "- 4/4→`100` · 3/4→`75` · 2/4→`50` · 1/4→`25` · 0/4→`0`",
        "",
        "**pension (연기금 지분 추세)** — 국민연금 등.",
        "- 보유+2분기 이상 지분 **순증**→`70`~`100`",
        "- 보유+보합(±0.1%p)→`50`",
        "- 보유+감소→`20`~`40`",
        "- 미보유 **확인**→`50` (중립). 모름→점수 `_____`",
        "- 자사주 소각 **분모효과만**으로 지분율↑ → 증가로 치지 말 것(`50` 또는 보수)",
        "",
        "**purpose (대량보유 투자목적)** — **최신** DART 대량보유보고 문구만.",
        "- 일반투자/단순투자→`100` · 경영참여/지배→`30` · 보고 없음→`50`",
        "- 2020~2023만 있고 이후 재확인 불가→점수 `_____`",
        "",
        "### T2 확정 기준 (C — true는 아래만)",
        "",
        "- `commercial_code_enforcement_decrees`: **관보 게재**만. 입법예고·보도→false",
        "- `msci_dm_index_inclusion_confirmed`: **MSCI 공식 편입 발표**만. 워치리스트→false",
        "- `ifrs18_domestic_adoption_schedule_confirmed`: **금융위 또는 한국회계기준원 확정 고시**만. "
        "검토·의견수렴→false",
        "- `fired:true`이면 출처에 1차 http(s) URL 필수. 못 찾으면 false.",
        "",
        "---",
        "",
        "## A_CECS_SUMMARY",
        "",
        "shortlist 30종 CECS 3축 요약. 종목 블록은 `## [TICKER] 이름` 형식을 유지하세요.",
        "각 축의 `점수 제안(0-100):`은 숫자만(또는 `_____`). 괄호·주석·한글을 붙이지 마세요.",
        "위 **CECS 3축 채점표**만 사용하세요. 축 의미를 임의로 재해석하지 마세요.",
        "",
    ]
    for subject in summary_subjects:
        lines.extend(_cecs_block(subject))
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## B_FINAL6_DEEP",
            "",
            "최종 제안 6종 심층(공시·환원·연기금·투자목적·리스크).",
            "",
        ]
    )
    for subject in deep_subjects:
        lines.extend(
            [
                f"### DEEP [{subject.ticker}] {subject.name}",
                f"- 섹터: {subject.sector or '—'}",
                "- 공시/지배구조: _____",
                "- 자사주·배당·환원: _____",
                "- 연기금·수급: _____",
                "- 투자목적: _____",
                "- 리스크: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## C_T2_EVENTS",
            "",
            "제도 이벤트 발생 여부. `fired`는 true/false만.",
            "**`근거`는 fired=false여도 한 줄 필수.** `_____`·빈칸이면 업로드 실패(영역 empty).",
            "true는 1차 출처(관보·MSCI 공식·금융위/KASB 고시) URL이 있을 때만.",
            "완성 예 (복붙 금지 — 형식만 참고):",
            "- fired: false",
            "- 근거: as_of 기준 MSCI 공식 DM 편입 발표 없음(워치리스트·전망만으로는 미확정)",
            "- 출처:",
            "  - 확인 불가; 검색 키워드: \"MSCI Korea DM inclusion official announcement\"",
            "",
        ]
    )
    for eid in t2_event_ids:
        lines.extend(
            [
                f"### EVENT [{eid}]",
                "- fired: false",
                "- 근거: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## D_THESIS",
            "",
            "**`근거` 필수.** damage=false여도 `_____`면 업로드 실패.",
            "완성 예: damage: false / 근거: as_of 기준 상법·밸류업 제도 후퇴·유예 확정 공시 없음",
            "",
            "### THESIS",
            "- damage: false",
            "- 근거: _____",
            "- 출처:",
            "  - ",
            "",
            "---",
            "",
            "## E_TARGET_VALUATION",
            "",
            "제안 종목 목표가/PBR. **`kr_alpha_exit_targets.yaml`은 요청서 생성만으로 지워지지 않습니다.**",
            "이미 승인된 종목은 아래 「이미 승인」에 **참고 숫자만** 적습니다 — AI가 덮어 쓰지 마세요.",
            "채울 대상은 「대기(채움)」공란만입니다. 승인 시 YAML에 반영되는 것도 대기 종목 위주입니다.",
            "`pbr_max`는 배수 숫자만(예: `0.75`), `target_price`는 원 단위 숫자만(예: `48000`).",
            "둘 중 최소 1개는 숫자. `배`/`원`/쉼표/범위(~)/증권사 주석은 근거 칸에만.",
            "**대기 종목:** `펀더멘털 사유`·`근거`·출처 URL≥1 필수. `_____`면 해당 종목 파싱 실패.",
            "",
        ]
    )
    exit_map = {
        str(k).zfill(6): dict(v)
        for k, v in (existing_exit or {}).items()
        if _exit_entry_has_usable_target(v)
    }
    already = [s for s in deep_subjects if s.ticker in exit_map]
    waiting_e = [s for s in deep_subjects if s.ticker not in exit_map]
    if already:
        lines.extend(
            [
                "### 이미 승인 (참고 · 채우지 말 것 · YAML 유지)",
                "",
                "아래는 `kr_alpha_exit_targets.yaml`에 있는 값입니다. "
                "재조사가 필요할 때만 운용자가 별도 보충/수정하세요. "
                "**이 블록을 AI가 다시 채워 업로드·승인하면 기존 PBR/목표가를 덮어쓸 수 있습니다.**",
                "",
            ]
        )
        for subject in already:
            entry = exit_map[subject.ticker]
            val = entry.get("valuation") if isinstance(entry.get("valuation"), dict) else {}
            pbr = val.get("pbr_max") if isinstance(val, dict) else None
            tp = entry.get("target_price")
            lines.extend(
                [
                    f"### TARGET_REF [{subject.ticker}] {subject.name}",
                    f"- pbr_max(승인): {pbr if pbr is not None else '—'}",
                    f"- target_price(승인): {tp if tp is not None else '—'}",
                    f"- approved_as_of: {entry.get('approved_as_of') or '—'}",
                    "- 상태: already_approved — **빈칸 채우기 금지**",
                    "",
                ]
            )
    lines.extend(
        [
            "### 대기 (채움 대상)",
            "",
        ]
    )
    if not waiting_e:
        lines.extend(
            [
                "(대기 종목 없음 — 제안 북 전 종목 목표가 승인됨. E 공란 없음.)",
                "",
            ]
        )
    for subject in waiting_e:
        lines.extend(
            [
                f"### TARGET [{subject.ticker}] {subject.name}",
                "- pbr_max: _____",
                "- target_price: _____",
                "- 펀더멘털 사유: _____",
                "- 근거: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "## F_QUANT_EVENTS",
            "",
            "정량 이벤트 감시(수동). **CECS/점수는 자동 변경되지 않음** — 재채점 검토 신호만.",
            "PyKRX/DART로는 컨센서스 EPS·목표가·등급을 자동 수집할 수 없음 "
            "(`docs/CONSENSUS_DATA_FEASIBILITY.md`).",
            "",
            "event_id 허용값: `earnings_surprise` | `rating_downgrade` | `target_gap_narrowed`",
            "해당 없으면 `event_id: _____` 로 두세요. 임계값(SUE/%)은 TODO.",
            "",
        ]
    )
    for subject in deep_subjects:
        lines.extend(
            [
                f"### SIGNAL [{subject.ticker}] {subject.name}",
                "- event_id: _____",
                "- note: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_weekly_qual_report(
    *,
    summary_subjects: Sequence[WeeklySubject],
    deep_subjects: Sequence[WeeklySubject],
    t2_event_ids: Sequence[str],
    docs_dir: Path,
    as_of: date | None = None,
    generated_at: datetime | None = None,
    input_paths: Sequence[Path] | None = None,
    journal_path: Path | None = None,
    existing_exit: Mapping[str, Mapping[str, Any]] | None = None,
) -> WeeklyQualReport:
    if not summary_subjects:
        raise ValueError("A_CECS_SUMMARY 대상이 없습니다.")
    if not deep_subjects:
        raise ValueError(
            "B/E(심층·목표가) 대상이 없습니다. proposal_book 최종 선정이 필요합니다."
        )
    generated_at = generated_at or datetime.now()
    as_of = as_of or generated_at.date()
    report_id = f"WQR-{generated_at.strftime('%Y%m%d-%H%M%S')}"
    input_snapshot_hash = _hash_inputs(input_paths or [])
    summary = tuple(_norm_subject(s) for s in summary_subjects)
    deep = tuple(_norm_subject(s) for s in deep_subjects)
    markdown = build_weekly_qual_markdown(
        summary_subjects=summary,
        deep_subjects=deep,
        t2_event_ids=t2_event_ids,
        as_of=as_of,
        generated_at=generated_at,
        report_id=report_id,
        input_snapshot_hash=input_snapshot_hash,
        existing_exit=existing_exit,
    )
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"weekly_qual_report_{generated_at.strftime('%Y%m%d')}.md"
    _atomic_write_text(path, markdown)
    append_record(
        action_kind="WEEKLY_QUAL_REPORT_GENERATED",
        as_of=as_of,
        subject=report_id,
        rationale=f"weekly qual request: {path.name}",
        payload={
            "path": str(path),
            "report_id": report_id,
            "input_snapshot_hash": input_snapshot_hash,
            "summary_tickers": [s.ticker for s in summary],
            "deep_tickers": [s.ticker for s in deep],
            "domains": list(DOMAIN_KEYS),
        },
        journal_path=journal_path,
    )
    return WeeklyQualReport(
        markdown=markdown,
        path=path,
        report_id=report_id,
        as_of=as_of,
        generated_at=generated_at,
        input_snapshot_hash=input_snapshot_hash,
        summary_tickers=tuple(s.ticker for s in summary),
        deep_tickers=tuple(s.ticker for s in deep),
    )


def parse_weekly_qual_markdown(text: str) -> WeeklyParseResult:
    meta = _parse_meta(text)
    sections = _split_sections(text)
    domain_failures: dict[str, list[str]] = {k: [] for k in DOMAIN_KEYS}
    domain_status: dict[str, str] = {k: "missing" for k in DOMAIN_KEYS}

    cecs_suggestions: tuple[ParsedResearchSuggestion, ...] = ()
    if "A_CECS_SUMMARY" in sections:
        parsed = parse_cecs_ai_research_markdown(sections["A_CECS_SUMMARY"])
        cecs_suggestions = parsed.suggestions
        if parsed.failures:
            domain_failures["cecs"].extend(parsed.failures)
        domain_status["cecs"] = (
            "ai_suggested" if cecs_suggestions else ("failed" if parsed.failures else "empty")
        )
    else:
        domain_failures["cecs"].append("A_CECS_SUMMARY 섹션 없음")

    deep_dives: list[ParsedDeepDive] = []
    if "B_FINAL6_DEEP" in sections:
        deep_dives, deep_fail = _parse_deep(sections["B_FINAL6_DEEP"])
        domain_failures["cecs"].extend(deep_fail)  # deep is CECS-adjacent qualitative
        # Deep alone must not mark CECS approvable — approve_domain reads `cecs` only.
    else:
        domain_failures["cecs"].append("B_FINAL6_DEEP 섹션 없음")

    t2_events: list[ParsedT2Event] = []
    if "C_T2_EVENTS" in sections:
        t2_events, t2_fail = _parse_t2(sections["C_T2_EVENTS"])
        domain_failures["t2"].extend(t2_fail)
        domain_status["t2"] = (
            "ai_suggested" if t2_events else ("failed" if t2_fail else "empty")
        )
    else:
        domain_failures["t2"].append("C_T2_EVENTS 섹션 없음")

    thesis: ParsedThesis | None = None
    if "D_THESIS" in sections:
        thesis, th_fail = _parse_thesis(sections["D_THESIS"])
        domain_failures["thesis"].extend(th_fail)
        domain_status["thesis"] = (
            "ai_suggested" if thesis is not None else ("failed" if th_fail else "empty")
        )
    else:
        domain_failures["thesis"].append("D_THESIS 섹션 없음")

    targets: list[ParsedTargetValuation] = []
    if "E_TARGET_VALUATION" in sections:
        targets, tg_fail = _parse_targets(sections["E_TARGET_VALUATION"])
        domain_failures["targets"].extend(tg_fail)
        domain_status["targets"] = (
            "ai_suggested" if targets else ("failed" if tg_fail else "empty")
        )
    else:
        domain_failures["targets"].append("E_TARGET_VALUATION 섹션 없음")

    quant_signals: list[dict[str, str]] = []
    if "F_QUANT_EVENTS" in sections:
        quant_signals = _parse_quant_signals(sections["F_QUANT_EVENTS"])

    return WeeklyParseResult(
        report_id=meta.get("report_id", ""),
        as_of=meta.get("as_of", ""),
        input_snapshot_hash=meta.get("input_snapshot_hash", ""),
        cecs_suggestions=cecs_suggestions,
        deep_dives=tuple(deep_dives),
        t2_events=tuple(t2_events),
        thesis=thesis,
        targets=tuple(targets),
        quant_signals=tuple(quant_signals),
        domain_failures={k: tuple(v) for k, v in domain_failures.items()},
        domain_status=domain_status,
    )


def suggestions_path(root: Path, lane: str = SUGGESTIONS_LANE_WEEKLY) -> Path:
    name = (
        SUGGESTIONS_FILE_MONTHLY
        if lane == SUGGESTIONS_LANE_MONTHLY
        else SUGGESTIONS_FILE_WEEKLY
    )
    return root / "data" / name


def lane_for_domain(domain: str) -> str:
    """CECS lives in the monthly store; C/D/E in the weekly store."""
    if str(domain or "").strip().lower() == "cecs":
        return SUGGESTIONS_LANE_MONTHLY
    return SUGGESTIONS_LANE_WEEKLY


def persist_weekly_suggestions(
    *,
    root: Path,
    parsed: WeeklyParseResult,
    report_name: str,
    as_of: date,
    journal_path: Path | None = None,
    locked_deep_tickers: Sequence[str] | None = None,
    lane: str = SUGGESTIONS_LANE_WEEKLY,
) -> Path:
    """Store domain-isolated AI suggestions without applying to engine inputs.

    ``lane=weekly`` → C/D/E only (``weekly_qual_suggestions.json``).
    ``lane=monthly`` → CECS only (``monthly_cecs_suggestions.json``).
    """
    lane = (
        SUGGESTIONS_LANE_MONTHLY
        if lane == SUGGESTIONS_LANE_MONTHLY
        else SUGGESTIONS_LANE_WEEKLY
    )
    out = suggestions_path(root, lane)
    previous: dict[str, Any] = {}
    if out.exists():
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    if lane == SUGGESTIONS_LANE_MONTHLY:
        domain_status = {
            k: (
                "ai_suggested"
                if k == "cecs" and parsed.domain_status.get("cecs") == "ai_suggested"
                else (
                    "empty"
                    if k != "cecs"
                    else (parsed.domain_status.get("cecs") or "empty")
                )
            )
            for k in DOMAIN_KEYS
        }
        for k in WEEKLY_DOMAIN_KEYS:
            domain_status[k] = "empty"
        payload = {
            "lane": lane,
            "report_id": parsed.report_id,
            "report_name": report_name,
            "as_of": as_of.isoformat(),
            "input_snapshot_hash": parsed.input_snapshot_hash,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "domain_status": domain_status,
            "domain_failures": {
                "cecs": list(parsed.domain_failures.get("cecs") or ()),
                "t2": [],
                "thesis": [],
                "targets": [],
            },
            "cecs": [_suggestion_dict(s) for s in parsed.cecs_suggestions],
            "deep_dives": [asdict(d) for d in parsed.deep_dives],
            "t2": [],
            "thesis": None,
            "targets": [],
            "deep_tickers": [],
            "source_reviewed": {k: [] for k in DOMAIN_KEYS},
            "approved": {k: False for k in DOMAIN_KEYS},
        }
    else:
        domain_status = {
            k: (
                "ai_suggested"
                if parsed.domain_status.get(k) == "ai_suggested"
                else "empty"
            )
            for k in DOMAIN_KEYS
        }
        domain_status["cecs"] = "empty"
        payload = {
            "lane": lane,
            "report_id": parsed.report_id,
            "report_name": report_name,
            "as_of": as_of.isoformat(),
            "input_snapshot_hash": parsed.input_snapshot_hash,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "domain_status": domain_status,
            "domain_failures": {
                "cecs": [],
                "t2": list(parsed.domain_failures.get("t2") or ()),
                "thesis": list(parsed.domain_failures.get("thesis") or ()),
                "targets": list(parsed.domain_failures.get("targets") or ()),
            },
            "cecs": [],
            "deep_dives": [asdict(d) for d in parsed.deep_dives],
            "t2": [asdict(e) for e in parsed.t2_events],
            "thesis": asdict(parsed.thesis) if parsed.thesis else None,
            "targets": [asdict(t) for t in parsed.targets],
            "deep_tickers": _resolve_locked_deep_tickers(
                locked_deep_tickers=locked_deep_tickers,
                previous=previous,
                deep_dives=parsed.deep_dives,
            ),
            "source_reviewed": {k: [] for k in DOMAIN_KEYS},
            "approved": {k: False for k in DOMAIN_KEYS},
        }
        allowed = {str(t).zfill(6) for t in (payload.get("deep_tickers") or [])}
        already_exit = {
            tk
            for tk, entry in load_exit_target_entries(root).items()
            if _exit_entry_has_usable_target(entry)
        }
        if allowed or already_exit:
            kept_targets: list[dict[str, Any]] = []
            dropped: list[str] = []
            protected: list[str] = []
            for row in payload.get("targets") or []:
                tk = str(row.get("ticker") or "").zfill(6)
                if not tk:
                    continue
                if allowed and tk not in allowed:
                    dropped.append(tk)
                    continue
                if tk in already_exit:
                    protected.append(tk)
                    continue
                kept_targets.append(row)
            payload["targets"] = kept_targets
            fails = list(payload.get("domain_failures", {}).get("targets") or [])
            if dropped:
                fails.append(
                    "최종 선정 밖 목표가 제외: " + ", ".join(sorted(set(dropped)))
                )
            if protected:
                fails.append(
                    "이미 YAML 승인된 목표가 유지(큐 제외): "
                    + ", ".join(sorted(set(protected)))
                )
            if dropped or protected:
                payload.setdefault("domain_failures", {})["targets"] = fails
            if not kept_targets and (dropped or protected or parsed.targets):
                payload["domain_status"]["targets"] = "empty"

    _preserve_unchanged_approvals(payload, previous)
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if lane == SUGGESTIONS_LANE_WEEKLY:
        _ingest_quant_signals(
            root=root,
            signals=parsed.quant_signals,
            as_of=as_of,
            journal_path=journal_path,
        )
    append_record(
        action_kind=(
            "WEEKLY_QUAL_IMPORT"
            if lane == SUGGESTIONS_LANE_WEEKLY
            else "MONTHLY_CECS_IMPORT"
        ),
        as_of=as_of,
        subject=parsed.report_id or report_name,
        rationale=(
            "weekly qual import → C/D/E ai_suggested"
            if lane == SUGGESTIONS_LANE_WEEKLY
            else "monthly CECS import → cecs ai_suggested"
        ),
        payload={
            "path": str(out),
            "lane": lane,
            "domain_status": payload["domain_status"],
            "failures": payload.get("domain_failures"),
        },
        journal_path=journal_path,
    )
    return out


def _preserve_unchanged_approvals(
    payload: dict[str, Any],
    previous: dict[str, Any],
) -> None:
    """Keep an approved domain only when the same report carries identical data."""
    if not previous:
        return
    same_report = (
        str(previous.get("report_id") or "") == str(payload.get("report_id") or "")
        and str(previous.get("input_snapshot_hash") or "")
        == str(payload.get("input_snapshot_hash") or "")
    )
    if not same_report:
        return

    domain_data_keys = {
        "cecs": ("cecs",),
        "t2": ("t2",),
        "thesis": ("thesis",),
        "targets": ("targets",),
    }
    for domain, keys in domain_data_keys.items():
        was_approved = bool((previous.get("approved") or {}).get(domain))
        unchanged = all(
            _json_equivalent(previous.get(key), payload.get(key))
            for key in keys
        )
        if not (was_approved and unchanged):
            continue
        payload["approved"][domain] = True
        payload["domain_status"][domain] = "approved"
        payload["source_reviewed"][domain] = list(
            (previous.get("source_reviewed") or {}).get(domain) or []
        )
        old_meta = (previous.get("approved_meta") or {}).get(domain)
        if old_meta is not None:
            payload.setdefault("approved_meta", {})[domain] = old_meta


def _json_equivalent(left: Any, right: Any) -> bool:
    """Compare persisted JSON data with dataclass/asdict tuples normalized."""
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
    )


def load_weekly_suggestions(
    root: Path,
    lane: str = SUGGESTIONS_LANE_WEEKLY,
) -> dict[str, Any]:
    path = suggestions_path(root, lane)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_split_legacy_combined_suggestions(root: Path) -> bool:
    """One-shot: move CECS out of weekly_qual_suggestions into monthly file."""
    weekly_path = suggestions_path(root, SUGGESTIONS_LANE_WEEKLY)
    monthly_path = suggestions_path(root, SUGGESTIONS_LANE_MONTHLY)
    if monthly_path.exists() or not weekly_path.exists():
        return False
    try:
        weekly = json.loads(weekly_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cecs_rows = list(weekly.get("cecs") or [])
    cecs_status = str((weekly.get("domain_status") or {}).get("cecs") or "empty")
    if not cecs_rows and cecs_status in {"empty", "missing", ""}:
        return False

    monthly = {
        "lane": SUGGESTIONS_LANE_MONTHLY,
        "report_id": weekly.get("report_id"),
        "report_name": weekly.get("report_name"),
        "as_of": weekly.get("as_of"),
        "input_snapshot_hash": weekly.get("input_snapshot_hash"),
        "imported_at": weekly.get("imported_at"),
        "migrated_from": SUGGESTIONS_FILE_WEEKLY,
        "domain_status": {
            "cecs": cecs_status
            if cecs_status != "empty"
            else ("ai_suggested" if cecs_rows else "empty"),
            "t2": "empty",
            "thesis": "empty",
            "targets": "empty",
        },
        "domain_failures": {
            "cecs": list((weekly.get("domain_failures") or {}).get("cecs") or []),
            "t2": [],
            "thesis": [],
            "targets": [],
        },
        "cecs": cecs_rows,
        "deep_dives": list(weekly.get("deep_dives") or []),
        "t2": [],
        "thesis": None,
        "targets": [],
        "deep_tickers": [],
        "source_reviewed": {
            "cecs": list((weekly.get("source_reviewed") or {}).get("cecs") or []),
            "t2": [],
            "thesis": [],
            "targets": [],
        },
        "approved": {
            "cecs": bool((weekly.get("approved") or {}).get("cecs")),
            "t2": False,
            "thesis": False,
            "targets": False,
        },
    }
    if (weekly.get("approved_meta") or {}).get("cecs") is not None:
        monthly["approved_meta"] = {
            "cecs": (weekly.get("approved_meta") or {}).get("cecs")
        }
    weekly["lane"] = SUGGESTIONS_LANE_WEEKLY
    weekly["cecs"] = []
    weekly.setdefault("domain_status", {})["cecs"] = "empty"
    weekly.setdefault("domain_failures", {})["cecs"] = []
    weekly.setdefault("source_reviewed", {})["cecs"] = []
    weekly.setdefault("approved", {})["cecs"] = False
    if "approved_meta" in weekly and "cecs" in (weekly.get("approved_meta") or {}):
        weekly["approved_meta"] = {
            k: v for k, v in (weekly.get("approved_meta") or {}).items() if k != "cecs"
        }

    monthly_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        monthly_path, json.dumps(monthly, ensure_ascii=False, indent=2) + "\n"
    )
    _atomic_write_text(
        weekly_path, json.dumps(weekly, ensure_ascii=False, indent=2) + "\n"
    )
    return True


def load_merged_qual_status(root: Path) -> dict[str, Any]:
    """Home/ops view: weekly C/D/E + monthly CECS status without sharing one file."""
    maybe_split_legacy_combined_suggestions(root)
    weekly = load_weekly_suggestions(root, SUGGESTIONS_LANE_WEEKLY)
    monthly = load_weekly_suggestions(root, SUGGESTIONS_LANE_MONTHLY)
    if not weekly and not monthly:
        return {}
    status = {
        k: (weekly.get("domain_status") or {}).get(k, "empty")
        for k in WEEKLY_DOMAIN_KEYS
    }
    status["cecs"] = (monthly.get("domain_status") or {}).get("cecs", "empty")
    approved = {
        k: bool((weekly.get("approved") or {}).get(k)) for k in WEEKLY_DOMAIN_KEYS
    }
    approved["cecs"] = bool((monthly.get("approved") or {}).get("cecs"))
    return {
        "domain_status": status,
        "approved": approved,
        "weekly": weekly,
        "monthly": monthly,
        "report_id": weekly.get("report_id") or monthly.get("report_id"),
        "as_of": weekly.get("as_of") or monthly.get("as_of"),
    }


def subjects_from_cecs_df(cecs_df: Any, *, limit: int | None = 30) -> list[WeeklySubject]:
    import pandas as pd

    if cecs_df is None or getattr(cecs_df, "empty", True):
        return []
    rows: list[WeeklySubject] = []
    for _, row in cecs_df.iterrows():
        rows.append(
            WeeklySubject(
                ticker=str(row.get("ticker", "")).zfill(6),
                name=str(row.get("name", "") or ""),
                sector=str(row.get("sector", "") or ""),
            )
        )
        if limit is not None and len(rows) >= limit:
            break
    return rows


def subjects_from_portfolio_rows(rows: Sequence[Any]) -> list[WeeklySubject]:
    out: list[WeeklySubject] = []
    for row in rows:
        out.append(
            WeeklySubject(
                ticker=str(getattr(row, "ticker", "")).zfill(6),
                name=str(getattr(row, "name", "") or ""),
                sector=str(getattr(row, "sector", "") or ""),
            )
        )
    return out


def _cecs_block(subject: WeeklySubject) -> list[str]:
    lines = [
        f"## [{subject.ticker}] {subject.name}",
        f"- 섹터: {subject.sector or '—'}",
        "",
    ]
    for axis in ("execution", "pension", "purpose"):
        lines.extend(
            [
                f"### {axis}",
                "- 점수 제안(0-100): _____",
                "- 근거: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )
    return lines


def _norm_subject(subject: WeeklySubject) -> WeeklySubject:
    return WeeklySubject(
        ticker=str(subject.ticker).zfill(6),
        name=(subject.name or "").strip(),
        sector=(subject.sector or "").strip(),
    )


def _hash_inputs(paths: Sequence[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p).lower()):
        if not path.exists():
            h.update(f"{path}=missing\n".encode("utf-8"))
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        h.update(f"{path.as_posix()}={digest}\n".encode("utf-8"))
    return h.hexdigest()[:16]


def _parse_meta(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("report_id", "as_of", "input_snapshot_hash"):
        m = re.search(rf"-\s*{key}:\s*`([^`]+)`", text)
        if m:
            out[key] = m.group(1).strip()
    return out


def _split_sections(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"^##\s+(A_CECS_SUMMARY|B_FINAL6_DEEP|C_T2_EVENTS|D_THESIS|E_TARGET_VALUATION)\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1)] = text[start:end].strip()
    return out


def _parse_sources(block: str) -> tuple[str, ...]:
    sources: list[str] = []
    in_sources = False
    for raw in block.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*-\s*출처\s*:", line):
            inline = line.split(":", 1)[1].strip()
            if inline and inline not in {"_____", ""}:
                sources.append(inline)
            in_sources = True
            continue
        if in_sources:
            m = re.match(r"^\s*-\s+(.+)$", line)
            if m:
                val = m.group(1).strip()
                if val and val != "_____":
                    sources.append(val)
            elif line.strip() and not line.strip().startswith("-"):
                in_sources = False
    if not sources:
        return ("확인 불가",)
    return tuple(sources)


def _field(block: str, label: str) -> str:
    m = re.search(rf"-\s*{re.escape(label)}\s*:\s*(.+)$", block, re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip()


def _parse_deep(text: str) -> tuple[list[ParsedDeepDive], list[str]]:
    chunks = re.split(r"(?m)^###\s+DEEP\s+\[", text)
    out: list[ParsedDeepDive] = []
    failures: list[str] = []
    for chunk in chunks[1:]:
        header, _, body = chunk.partition("\n")
        hm = re.match(r"(\d{6})\]\s*(.*)$", header.strip())
        if not hm:
            failures.append(f"DEEP 헤더 파싱 실패: {header[:40]}")
            continue
        ticker, name = hm.group(1), hm.group(2).strip()
        sources = _parse_sources(body)
        out.append(
            ParsedDeepDive(
                ticker=ticker,
                name=name,
                disclosure=_field(body, "공시/지배구조") or "확인 불가",
                buyback_dividend=_field(body, "자사주·배당·환원") or "확인 불가",
                pension=_field(body, "연기금·수급") or "확인 불가",
                investment_purpose=_field(body, "투자목적") or "확인 불가",
                risks=_field(body, "리스크") or "확인 불가",
                sources=sources,
            )
        )
    return out, failures


def _parse_t2(text: str) -> tuple[list[ParsedT2Event], list[str]]:
    chunks = re.split(r"(?m)^###\s+EVENT\s+\[", text)
    out: list[ParsedT2Event] = []
    failures: list[str] = []
    for chunk in chunks[1:]:
        header, _, body = chunk.partition("\n")
        eid = header.strip().rstrip("]")
        if not eid:
            failures.append("EVENT id 없음")
            continue
        fired_raw = _field(body, "fired").lower()
        if fired_raw not in {"true", "false"}:
            failures.append(f"{eid}: fired는 true/false 필요")
            continue
        rationale = _field(body, "근거")
        if not rationale or rationale == "_____":
            failures.append(f"{eid}: 근거 필요")
            continue
        out.append(
            ParsedT2Event(
                event_id=eid,
                fired=fired_raw == "true",
                rationale=rationale,
                sources=_parse_sources(body),
            )
        )
    return out, failures


def _parse_thesis(text: str) -> tuple[ParsedThesis | None, list[str]]:
    m = re.search(r"(?ms)^###\s+THESIS\s*$(.*)", text)
    if not m:
        return None, ["THESIS 블록 없음"]
    body = m.group(1)
    damage_raw = _field(body, "damage").lower()
    if damage_raw not in {"true", "false"}:
        return None, ["damage는 true/false 필요"]
    rationale = _field(body, "근거")
    if not rationale or rationale == "_____":
        return None, ["논지 근거 필요"]
    return (
        ParsedThesis(
            damage=damage_raw == "true",
            rationale=rationale,
            sources=_parse_sources(body),
        ),
        [],
    )


def _parse_targets(text: str) -> tuple[list[ParsedTargetValuation], list[str]]:
    # TARGET_REF(이미 승인 참고)는 제외 — `TARGET` 뒤에 공백+[ 만 매칭.
    chunks = re.split(r"(?m)^###\s+TARGET(?!_REF)\s+\[", text)
    out: list[ParsedTargetValuation] = []
    failures: list[str] = []
    for chunk in chunks[1:]:
        header, _, body = chunk.partition("\n")
        hm = re.match(r"(\d{6})\]\s*(.*)$", header.strip())
        if not hm:
            failures.append(f"TARGET 헤더 파싱 실패: {header[:40]}")
            continue
        ticker, name = hm.group(1), hm.group(2).strip()
        fund_reason = _field(body, "펀더멘털 사유")
        rationale = _field(body, "근거")
        if not fund_reason or fund_reason == "_____":
            failures.append(f"{ticker}: 펀더멘털 사유 필요")
            continue
        if not rationale or rationale == "_____":
            failures.append(f"{ticker}: 근거 필요")
            continue
        pbr_raw = _field(body, "pbr_max")
        price_raw = _field(body, "target_price")
        pbr = _float_blank(pbr_raw)
        price = _float_blank(price_raw)
        if pbr is None and price is None:
            failures.append(f"{ticker}: pbr_max 또는 target_price 필요")
            continue
        sources = _parse_sources(body)
        if sources == ("확인 불가",):
            failures.append(f"{ticker}: 출처 필요")
            continue
        out.append(
            ParsedTargetValuation(
                ticker=ticker,
                name=name,
                pbr_max=pbr,
                target_price=price,
                rationale=rationale,
                sources=sources,
                fundamental_reason=fund_reason,
            )
        )
    return out, failures


def _parse_quant_signals(text: str) -> list[dict[str, str]]:
    """Optional F_QUANT_EVENTS — blank event_id ignored; never fails domain gates."""
    from alpha_system.scoring.rescore import CONSENSUS_TRIGGER_IDS

    chunks = re.split(r"(?m)^###\s+SIGNAL\s+\[", text)
    out: list[dict[str, str]] = []
    for chunk in chunks[1:]:
        header, _, body = chunk.partition("\n")
        hm = re.match(r"(\d{6})\]\s*(.*)$", header.strip())
        if not hm:
            continue
        ticker = hm.group(1)
        eid = (_field(body, "event_id") or "").strip()
        if not eid or eid == "_____" or eid not in CONSENSUS_TRIGGER_IDS:
            continue
        out.append(
            {
                "ticker": ticker,
                "event_id": eid,
                "note": (_field(body, "note") or "").strip(),
            }
        )
    return out


def _ingest_quant_signals(
    *,
    root: Path,
    signals: Sequence[dict[str, str]],
    as_of: date,
    journal_path: Path | None,
) -> None:
    """Queue human rescore review from manual F signals — never changes scores."""
    if not signals:
        return
    from alpha_system.scoring.pending_rescore import pending_path, upsert_pending
    from alpha_system.scoring.rescore import (
        build_rescore_queue_item,
        evaluate_manual_consensus_signals,
    )

    decision = evaluate_manual_consensus_signals(list(signals), as_of=as_of)
    tickers = [str(s.get("ticker") or "") for s in signals if s.get("ticker")]
    item = build_rescore_queue_item(
        decision, as_of=as_of, tickers=tickers, source="weekly_f_quant"
    )
    if item is None:
        return
    payload = {
        "key": item.key,
        "title": item.title,
        "detail": item.detail,
        "triggers": list(item.triggers),
        "tickers": list(item.tickers),
        "as_of": item.as_of,
        "source": item.source,
        "signals": list(signals),
    }
    upsert_pending(payload, path=pending_path(root))
    append_record(
        action_kind="RESCORE_TRIGGER_FIRED",
        as_of=as_of,
        subject="weekly_f_quant",
        rationale=item.detail,
        payload={**payload, "scores_auto_changed": False},
        journal_path=journal_path,
    )


def _float_blank(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text or text in {"_____", "확인 불가", "-"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _resolve_locked_deep_tickers(
    *,
    locked_deep_tickers: Sequence[str] | None,
    previous: Mapping[str, Any],
    deep_dives: Sequence[Any],
) -> list[str]:
    """Proposal-book allowlist only — never expand from targets section."""
    if locked_deep_tickers:
        return sorted(
            {
                str(t).zfill(6)
                for t in locked_deep_tickers
                if str(t).strip()
            }
        )
    prev = previous.get("deep_tickers") or []
    if prev:
        return sorted({str(t).zfill(6) for t in prev if str(t).strip()})
    return sorted(
        {
            str(getattr(d, "ticker", "") or "").zfill(6)
            for d in deep_dives
            if getattr(d, "ticker", None)
        }
    )


def _suggestion_dict(suggestion: ParsedResearchSuggestion) -> dict[str, Any]:
    def axis(a: ParsedResearchAxis) -> dict[str, Any]:
        return {
            "score_100": a.score_100,
            "rationale": a.rationale,
            "sources": list(a.sources),
            "provisional": bool(getattr(a, "provisional", False)),
        }

    return {
        "ticker": suggestion.ticker,
        "name": suggestion.name,
        "execution": axis(suggestion.execution),
        "pension": axis(suggestion.pension),
        "purpose": axis(suggestion.purpose),
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def load_exit_target_entries(root: Path) -> dict[str, dict[str, Any]]:
    """ticker → exit YAML entry (may be empty dict)."""
    import yaml

    path = root / "data" / "kr_alpha_exit_targets.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    tickers = data.get("tickers") or {}
    out: dict[str, dict[str, Any]] = {}
    for raw_tk, entry in tickers.items():
        tk = str(raw_tk).zfill(6)
        if isinstance(entry, dict):
            out[tk] = entry
    return out


def _exit_entry_has_usable_target(entry: Mapping[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("target_price") is not None and str(entry.get("target_price")).strip() != "":
        return True
    val = entry.get("valuation")
    return isinstance(val, dict) and val.get("pbr_max") is not None


def load_exit_target_tickers(root: Path) -> set[str]:
    """Tickers with usable approved exit valuation (pbr_max or target_price)."""
    return {
        tk
        for tk, entry in load_exit_target_entries(root).items()
        if _exit_entry_has_usable_target(entry)
    }


def waiting_target_subjects(
    proposal_rows: Sequence[Any],
    *,
    root: Path,
) -> list[WeeklySubject]:
    """Proposal-book names that still lack approved exit target valuation."""
    have = load_exit_target_tickers(root)
    waiting: list[WeeklySubject] = []
    for row in subjects_from_portfolio_rows(proposal_rows):
        if row.ticker not in have:
            waiting.append(row)
    return waiting


_PROMPT_FALLBACK_B = """당신은 한국 상장주식 목표가(익절·밸류 상한) 조사 보조입니다.
첨부는 E_TARGET_VALUATION만 있는 보충 요청서입니다.
첨부된 모든 `### TARGET [티커] 이름`만 채우세요. 헤더·필드명 변경 금지.

규칙:
1. pbr_max = 배수 숫자만 또는 _____. target_price = 원 단위 정수만 또는 _____.
2. 둘 중 최소 1개는 숫자. 펀더멘털 사유·근거·출처 URL 필수.
3. 기존 목표가 맹목 복사 금지. 첨부 as_of 기준 재조사.
4. 복수 출처 교차확인. 실적 공시 이후 리포트를 우선.
5. 극단 괴리 시 보수값 또는 근거에 편차 명시.
6. 매수 추천·target_portfolio 변경 제안 금지.
7. 설명 없이 완성 Markdown만 출력.

[아래에 보충 요청서 Markdown 전체를 붙이세요]
"""


_PROMPT_FALLBACK_C = """당신은 한국 상장주식 CECS(정성) 조사 보조입니다.
첨부는 SAA 알파 월간 CECS 요청서입니다. 첨부 as_of·티커·채점표·헤더를 그대로 따르세요.

# 범위
- A_CECS_SUMMARY만 채우세요. C/D/E는 손대지 마세요.

# 절대 규칙
1. 헤더·필드 라벨 불변. 추정 금지. as_of 기준.
2. target_portfolio 변경·매수 추천·순위 변경 제안 금지.
3. 완성 Markdown만 출력.

# A_CECS_SUMMARY
첨부된 모든 `## [티커]` 블록의 execution / pension / purpose를 채우세요.
점수는 첨부 채점표만. 근거·출처(URL) 필수.

[아래에 월간 CECS 요청서 Markdown 전체를 붙이세요]
"""


def load_cde_copy_prompt(
    root: Path | None = None,
    *,
    which: str = "B",
) -> str:
    """Load Claude copy-paste prompt A (weekly), B (targets), or C (monthly CECS).

    Source of truth: ``docs/WEEKLY_QUAL_CDE_PROMPT.md`` fenced ``text`` block
    under the matching heading. Falls back to embedded prompts if missing.
    """
    which = str(which or "B").strip().upper()
    if which not in {"A", "B", "C"}:
        which = "B"
    docs = (Path(root) if root else Path.cwd()) / "docs" / "WEEKLY_QUAL_CDE_PROMPT.md"
    if docs.exists():
        try:
            text = docs.read_text(encoding="utf-8")
        except OSError:
            text = ""
        heading = {
            "A": "## 복사용 프롬프트 A",
            "B": "## 복사용 프롬프트 B",
            "C": "## 복사용 프롬프트 C",
        }[which]
        idx = text.find(heading)
        if idx >= 0:
            chunk = text[idx:]
            fence = chunk.find("```text")
            if fence >= 0:
                body = chunk[fence + len("```text") :]
                end = body.find("```")
                if end >= 0:
                    prompt = body[:end].strip()
                    if prompt:
                        return prompt + "\n"
    if which == "C":
        return _PROMPT_FALLBACK_C
    if which == "A":
        # Prefer A from docs; if missing, CDE-oriented fallback from B+T2 hint.
        return (
            "당신은 한국 상장주식 주간 정성 조사 보조입니다.\n"
            "첨부 Markdown의 C_T2_EVENTS → D_THESIS → E_TARGET_VALUATION만 채우세요.\n"
            "헤더·필드 불변. 추정 금지. target_portfolio 변경 금지. 완성 Markdown만.\n\n"
            "[아래에 요청서 Markdown 전체를 붙이세요]\n"
        )
    return _PROMPT_FALLBACK_B


def build_targets_supplement_markdown(
    *,
    waiting_subjects: Sequence[WeeklySubject],
    proposal_tickers: Sequence[str],
    as_of: date,
    generated_at: datetime,
    report_id: str,
) -> str:
    """E-only request for waiting candidates (no A–D redo)."""
    subjects = tuple(_norm_subject(s) for s in waiting_subjects)
    prop = sorted({str(t).zfill(6) for t in proposal_tickers if str(t).strip()})
    lines = [
        "# 목표가 대기 후보 보충 요청서 (E only)",
        "",
        f"- report_id: `{report_id}`",
        f"- as_of: `{as_of.isoformat()}`",
        f"- generated_at: `{generated_at.isoformat(timespec='seconds')}`",
        "- mode: `targets_supplement`",
        f"- proposal_tickers: `{', '.join(prop)}`",
        f"- waiting_tickers: `{', '.join(s.ticker for s in subjects)}`",
        "",
        f"> {USAGE_WARNING}",
        "",
        "이 파일은 **목표가(E)만** 채웁니다. CECS/T2/논지는 건드리지 마세요.",
        "대상은 현재 제안 북 중 목표가 미승인(대기) 종목뿐입니다.",
        "",
        "## 파서 계약 (업로드 필수 — 위반 시 거부)",
        "",
        "1. `### TARGET [티커] 이름` 헤더와 아래 **5개 필드 라벨**을 바꾸지 마세요.",
        "2. `pbr_max:` → 배수 **숫자만** (예: `1.05`). 금지: `1.0~1.1배`, `약 1.0`, 볼드/표.",
        "3. `target_price:` → 원 단위 **정수만** (예: `37500`). 금지: `37,000원`, `37000~38000`, `약`.",
        "4. `펀더멘털 사유:` / `근거:` → 한 줄 이상 문장. `_____`·빈칸·`####` 소제목만으로는 불가.",
        "5. `출처:` 아래 `- https://...` URL ≥1.",
        "6. 조사 메모·표·증권사 비교는 **근거 칸 문장 안**에만. 필드 구조를 에세이로 바꾸지 마세요.",
        "7. 프롬프트: `docs/WEEKLY_QUAL_CDE_PROMPT.md` 의 **프롬프트 B**.",
        "",
        "완성 예 (형식만):",
        "```",
        "### TARGET [175330] JB금융지주",
        "- pbr_max: 1.05",
        "- target_price: 37500",
        "- 펀더멘털 사유: ROE·환원 가이던스 근거 한 줄",
        "- 근거: 교차확인 요약 한 줄",
        "- 출처:",
        "  - https://example.com/report",
        "```",
        "",
        "---",
        "",
        "## E_TARGET_VALUATION",
        "",
    ]
    for subject in subjects:
        lines.extend(
            [
                f"### TARGET [{subject.ticker}] {subject.name}",
                "- pbr_max: _____",
                "- target_price: _____",
                "- 펀더멘털 사유: _____",
                "- 근거: _____",
                "- 출처:",
                "  - ",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_targets_supplement_report(
    *,
    waiting_subjects: Sequence[WeeklySubject],
    proposal_tickers: Sequence[str],
    docs_dir: Path,
    as_of: date | None = None,
    generated_at: datetime | None = None,
    journal_path: Path | None = None,
) -> WeeklyQualReport:
    if not waiting_subjects:
        raise ValueError("대기 후보(목표가 미승인)가 없습니다.")
    generated_at = generated_at or datetime.now()
    as_of = as_of or generated_at.date()
    report_id = f"WQR-E-{generated_at.strftime('%Y%m%d-%H%M%S')}"
    waiting = tuple(_norm_subject(s) for s in waiting_subjects)
    prop = sorted({str(t).zfill(6) for t in proposal_tickers if str(t).strip()})
    markdown = build_targets_supplement_markdown(
        waiting_subjects=waiting,
        proposal_tickers=prop,
        as_of=as_of,
        generated_at=generated_at,
        report_id=report_id,
    )
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"weekly_qual_targets_supplement_{generated_at.strftime('%Y%m%d')}.md"
    _atomic_write_text(path, markdown)
    append_record(
        action_kind="WEEKLY_TARGETS_SUPPLEMENT_GENERATED",
        as_of=as_of,
        subject=report_id,
        rationale=f"targets supplement request: {path.name}",
        payload={
            "path": str(path),
            "report_id": report_id,
            "waiting_tickers": [s.ticker for s in waiting],
            "proposal_tickers": prop,
            "domains": ["targets"],
        },
        journal_path=journal_path,
    )
    return WeeklyQualReport(
        markdown=markdown,
        path=path,
        report_id=report_id,
        as_of=as_of,
        generated_at=generated_at,
        input_snapshot_hash="",
        summary_tickers=(),
        deep_tickers=tuple(s.ticker for s in waiting),
    )


def persist_targets_supplement(
    *,
    root: Path,
    parsed: WeeklyParseResult,
    report_name: str,
    as_of: date,
    proposal_tickers: Sequence[str],
    waiting_tickers: Sequence[str],
    journal_path: Path | None = None,
) -> Path:
    """Merge E-only upload into suggestions without wiping other domains."""
    if not parsed.targets:
        fails = list(parsed.domain_failures.get("targets") or ())
        hint = (
            " 파서 거부: " + "; ".join(fails)
            if fails
            else " E 섹션에 ### TARGET 블록·필수 필드가 없습니다."
        )
        raise ValueError(
            "목표가 제안이 없습니다. E_TARGET_VALUATION을 채우세요."
            + hint
            + " (pbr_max/target_price=순수숫자, 펀더멘털 사유·근거·출처 URL 필수."
            " 에세이·표·범위표기 금지 — 요청서「파서 계약」·프롬프트 B 참고)"
        )
    prop = sorted({str(t).zfill(6) for t in proposal_tickers if str(t).strip()})
    waiting = {str(t).zfill(6) for t in waiting_tickers if str(t).strip()}
    if not prop:
        raise ValueError("proposal_tickers(최종 선정)가 필요합니다.")
    for t in parsed.targets:
        tk = str(t.ticker).zfill(6)
        if tk not in prop:
            raise ValueError(
                f"목표가 보충 거부: 최종 선정 밖 종목 {tk}. "
                "현재 proposal_book 기준으로 다시 생성하세요."
            )
        if waiting and tk not in waiting:
            raise ValueError(
                f"목표가 보충 거부: 대기 목록에 없는 종목 {tk}."
            )

    maybe_split_legacy_combined_suggestions(root)
    out = suggestions_path(root, SUGGESTIONS_LANE_WEEKLY)
    previous = load_weekly_suggestions(root, SUGGESTIONS_LANE_WEEKLY)
    payload = dict(previous) if previous else {}
    payload.setdefault("domain_status", {k: "empty" for k in DOMAIN_KEYS})
    payload.setdefault("domain_failures", {k: [] for k in DOMAIN_KEYS})
    payload.setdefault("source_reviewed", {k: [] for k in DOMAIN_KEYS})
    payload.setdefault("approved", {k: False for k in DOMAIN_KEYS})
    payload["report_id"] = parsed.report_id or payload.get("report_id") or "WQR-E"
    payload["report_name"] = report_name
    payload["as_of"] = as_of.isoformat()
    payload["imported_at"] = datetime.now().isoformat(timespec="seconds")
    payload["mode"] = "targets_supplement"
    payload["deep_tickers"] = prop
    # 대기(waiting) 종목만 승인 큐에 둔다.
    # 이미 YAML에 승인된 종목·비대기 prior를 큐에 남기면 재승인 시 덮어쓰기됨.
    new_by = {
        str(t.ticker).zfill(6): asdict(t) for t in parsed.targets
    }
    prior_still_waiting = [
        t
        for t in (payload.get("targets") or [])
        if isinstance(t, Mapping)
        and str(t.get("ticker") or "").zfill(6) in waiting
        and str(t.get("ticker") or "").zfill(6) not in new_by
    ]
    payload["targets"] = prior_still_waiting + list(new_by.values())
    payload["domain_status"]["targets"] = "ai_suggested"
    payload["domain_failures"]["targets"] = list(
        (parsed.domain_failures or {}).get("targets") or []
    )
    payload["source_reviewed"]["targets"] = []
    payload["approved"]["targets"] = False
    payload["lane"] = SUGGESTIONS_LANE_WEEKLY
    payload["cecs"] = []
    payload.setdefault("domain_status", {})["cecs"] = "empty"
    payload.setdefault("domain_failures", {})["cecs"] = []
    payload.setdefault("source_reviewed", {})["cecs"] = []
    payload.setdefault("approved", {})["cecs"] = False

    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    append_record(
        action_kind="WEEKLY_TARGETS_SUPPLEMENT_IMPORT",
        as_of=as_of,
        subject=str(payload.get("report_id") or report_name),
        rationale="targets supplement import → targets ai_suggested only",
        payload={
            "path": str(out),
            "waiting_tickers": sorted(waiting),
            "proposal_tickers": prop,
            "target_tickers": [str(t.ticker).zfill(6) for t in parsed.targets],
        },
        journal_path=journal_path,
    )
    return out


# Keep CecsResearchSubject import available for callers that adapt lists.
__all__ = [
    "DOMAIN_KEYS",
    "maybe_split_legacy_combined_suggestions",
    "load_merged_qual_status",
    "lane_for_domain",
    "suggestions_path",
    "MONTHLY_DOMAIN_KEYS",
    "WEEKLY_DOMAIN_KEYS",
    "SUGGESTIONS_LANE_MONTHLY",
    "SUGGESTIONS_LANE_WEEKLY",
    "SECTION_IDS",
    "WeeklySubject",
    "WeeklyQualReport",
    "WeeklyParseResult",
    "build_weekly_qual_markdown",
    "write_weekly_qual_report",
    "parse_weekly_qual_markdown",
    "persist_weekly_suggestions",
    "persist_targets_supplement",
    "load_weekly_suggestions",
    "load_exit_target_entries",
    "load_exit_target_tickers",
    "waiting_target_subjects",
    "build_targets_supplement_markdown",
    "write_targets_supplement_report",
    "load_cde_copy_prompt",
    "subjects_from_cecs_df",
    "subjects_from_portfolio_rows",
    "CecsResearchSubject",
]
