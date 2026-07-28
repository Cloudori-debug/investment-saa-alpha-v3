"""Build AI verification markdown report (facts the system cannot observe)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from alpha_system.journal import append_record
from alpha_system.ui.services.context import DashboardContext, PortfolioRow
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


@dataclass(frozen=True)
class AiVerificationReport:
    markdown: str
    path: Path
    generated_at: datetime


def build_ai_verification_markdown(ctx: DashboardContext, *, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now()
    copy = load_ui_copy().get("ai_verification") or {}
    usage = copy_get(
        "ai_verification",
        "usage_banner",
        default="AI 답변은 참고용. 출처 원문을 직접 확인한 후에만 이벤트 입력을 진행하세요.",
    )

    status = "PRE_LAUNCH" if ctx.pre_launch else "가동"
    go_live = (
        ctx.effective_go_live.isoformat()
        if ctx.effective_go_live is not None
        else "—"
    )

    lines: list[str] = [
        "# AI 검증 리포트",
        "",
        f"- 생성일시: `{generated_at.isoformat(timespec='seconds')}`",
        f"- 시스템 상태: **{status}** (go_live={go_live})",
        f"- 대시보드 as_of: `{ctx.as_of.isoformat()}`",
        "",
        "## 데이터 as_of",
        "",
    ]
    for src in ctx.source_status:
        as_of_s = src.as_of.isoformat() if src.as_of else "—"
        stale = " (갱신 필요)" if src.stale else ""
        lines.append(f"- {src.label}: `{as_of_s}`{stale} — `{src.path}`")
    lines.extend(["", "---", "", "## 사용 안내", "", f"> {usage}", ""])

    lines.extend(["## 1. 검증 질문 (시스템 관측 불가 사실)", ""])
    lines.extend(_t2_questions(copy, ctx))
    lines.extend(_thesis_questions(copy))
    lines.extend(_holdings_questions(copy, ctx))

    lines.extend(["", "## 2. AI 답변 규칙", ""])
    rules = copy.get("answer_rules") or []
    if isinstance(rules, list):
        for i, rule in enumerate(rules, 1):
            lines.append(f"{i}. {rule}")
    lines.extend(
        [
            "",
            "## 3. 답변 작성란 (AI 또는 운용자)",
            "",
            "_아래에 질문별로 답변·1차 출처 URL을 기입하세요._",
            "",
            "```",
            "(답변)",
            "```",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_ai_verification_report(
    ctx: DashboardContext,
    *,
    docs_dir: Path | None = None,
    generated_at: datetime | None = None,
    journal: bool = True,
) -> AiVerificationReport:
    generated_at = generated_at or datetime.now()
    md = build_ai_verification_markdown(ctx, generated_at=generated_at)
    docs_dir = docs_dir or (ctx.root / "docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d")
    path = docs_dir / f"ai_verification_report_{stamp}.md"
    # same-day re-run: keep single file for the calendar day (overwrite)
    path.write_text(md, encoding="utf-8")

    if journal:
        try:
            rel = str(path.relative_to(ctx.root)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        append_record(
            action_kind="AI_VERIFICATION_REPORT",
            as_of=generated_at.date(),
            subject="*",
            rationale=f"AI verification report written: {path.name}",
            payload={
                "path": rel,
                "system_status": "PRE_LAUNCH" if ctx.pre_launch else "LIVE",
                "go_live": (
                    ctx.effective_go_live.isoformat()
                    if ctx.effective_go_live
                    else None
                ),
            },
        )
    return AiVerificationReport(markdown=md, path=path, generated_at=generated_at)


def _t2_questions(copy: dict[str, Any], ctx: DashboardContext) -> list[str]:
    lines = ["### a. T2 제도 이벤트 (각 1건)", ""]
    events = copy.get("t2_events") or {}
    event_ids = list(ctx.cfg.tranches["T2"].event_ids)
    for eid in event_ids:
        spec = events.get(eid) or {}
        label = spec.get("label") or eid
        q = spec.get("question") or f"{label} 발생 여부?"
        crit = spec.get("confirm_criterion") or ""
        fired = eid in ctx.runtime.effective_events()
        lines.append(f"#### {label} (`{eid}`)")
        lines.append("")
        lines.append(f"- **질문:** {q}")
        lines.append(f"- **확정 인정 기준:** {crit}")
        lines.append(
            f"- **시스템 기록 상태:** {'이미 저널/런타임에 기록됨' if fired else '미기록 (수동 입력 대기)'}"
        )
        lines.append("")
    return lines


def _thesis_questions(copy: dict[str, Any]) -> list[str]:
    td = copy.get("thesis_damage") or {}
    return [
        "### b. 논지 훼손 징후",
        "",
        f"- **질문:** {td.get('question', '')}",
        f"- **참고:** {td.get('note', '')}",
        "",
    ]


def _holdings_questions(copy: dict[str, Any], ctx: DashboardContext) -> list[str]:
    hd = copy.get("holdings_disclosure") or {}
    lines = [
        "### c. 보유 종목 주주환원 정책 변경 공시",
        "",
        f"- **질문:** {hd.get('question', '')}",
        f"- **참고:** {hd.get('note', '')}",
        "",
    ]
    if ctx.pre_launch:
        lines.append("- **적용:** PRE_LAUNCH — 본 섹션은 가동 후 답변 대상입니다. (지금은 생략 가능)")
        lines.append("")
        return lines
    lines.append("- **보유 kr_alpha 종목:**")
    rows: Sequence[PortfolioRow] = ctx.portfolio_rows or []
    if not rows:
        lines.append("  - (보유 없음)")
    else:
        for row in rows:
            lines.append(f"  - `{row.ticker}` {row.name}")
    lines.append("")
    return lines
