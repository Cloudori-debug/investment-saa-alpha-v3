"""Status / performance-hook / discretionary-deviation reports (§7.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional, Sequence

from alpha_system.entry.evaluate import EntryEvaluation
from alpha_system.journal.recorder import JournalRecord, list_discretionary_warnings, list_entries
from alpha_system.schema import AlphaSystemConfig
from alpha_system.scoring.engine import NameScore
from alpha_system.swap.observe import SwapCandidate


@dataclass
class ExecutionFill:
    """Minimal fill record for performance tracking (benchmark compare is TODO)."""

    ticker: str
    as_of: date
    side: str  # buy | sell
    price: float
    weight: float = 0.0
    notes: str = ""


@dataclass
class StatusReportInput:
    as_of: date
    entry: EntryEvaluation
    scores: Sequence[NameScore] = field(default_factory=list)
    fills: Sequence[ExecutionFill] = field(default_factory=list)
    swap_candidates: Sequence[SwapCandidate] = field(default_factory=list)


def days_to_window_end(cfg: AlphaSystemConfig, as_of: date) -> int:
    return (cfg.thesis_window.window_end - as_of).days


def render_discretionary_section(
    entries: Sequence[JournalRecord] | None = None,
) -> str:
    rows = list(entries) if entries is not None else list_discretionary_warnings()
    lines = [
        "## 재량 이탈 (WARN_DISCRETIONARY)",
        "",
        f"- 누적 횟수: **{len(rows)}**",
        "",
        "이탈이 반복되면 운용자 문제가 아니라 **규칙이 현실과 안 맞는다**는 신호로 읽는다.",
        "",
    ]
    if not rows:
        lines.append("_기록 없음._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| entry_id | as_of | subject | discretionary_reason | rationale |")
    lines.append("|---|---|---|---|---|")
    for e in rows:
        reason = (e.discretionary_reason or "").replace("|", "/")
        rationale = (e.rationale or "").replace("|", "/")
        lines.append(
            f"| {e.entry_id} | {e.as_of} | {e.subject} | {reason} | {rationale} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_performance_hook(
    cfg: AlphaSystemConfig,
    fills: Sequence[ExecutionFill],
) -> str:
    lines = [
        "## 성과 추적",
        "",
        f"- fills recorded: **{len(fills)}**",
        f"- benchmark: `{cfg.benchmark}` "
        + (
            "([TODO] unset — comparison hook only)"
            if cfg.benchmark is None
            else "(configured)"
        ),
        "",
    ]
    if not fills:
        lines.append("_집행 단가 기록 없음._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| as_of | ticker | side | price | weight | notes |")
    lines.append("|---|---|---|---:|---:|---|")
    for f in fills:
        lines.append(
            f"| {f.as_of.isoformat()} | {f.ticker} | {f.side} | {f.price} | "
            f"{f.weight} | {f.notes} |"
        )
    lines.append("")
    if cfg.benchmark is None:
        lines.append(
            "> 벤치마크 대비 초과수익 계산은 `benchmark` TODO 확정 전까지 수행하지 않음."
        )
        lines.append("")
    return "\n".join(lines)


def render_status_report(
    cfg: AlphaSystemConfig,
    data: StatusReportInput,
) -> str:
    remaining = days_to_window_end(cfg, data.as_of)
    lines = [
        "# 알파 시스템 — 상태 리포트",
        "",
        f"- as_of: `{data.as_of.isoformat()}`",
        f"- window_end: `{cfg.thesis_window.window_end.isoformat()}`",
        f"- days_to_window_end: **{remaining}**",
        f"- capital_max_fraction: `{cfg.capital.max_fraction_of_total_assets}`",
        f"- score_cutoff: `{cfg.scoring.score_cutoff}`",
        "",
        "## 트랜치 상태",
        "",
        "| tranche | state | trigger_met | weight | detail |",
        "|---|---|---|---:|---|",
    ]
    for st in data.entry.statuses:
        lines.append(
            f"| {st.tranche_id.value} | {st.state.value} | {st.trigger_met} | "
            f"{st.weight} | {st.detail.replace('|', '/')} |"
        )
    lines.append("")

    lines.append("## 트리거·액션 (이번 평가)")
    lines.append("")
    if not data.entry.actions:
        lines.append("_액션 없음._")
        lines.append("")
    else:
        lines.append("| type | tranche | reason |")
        lines.append("|---|---|---|")
        for a in data.entry.actions:
            lines.append(
                f"| {a.action_type.value} | {a.tranche_id.value} | "
                f"{a.reason.replace('|', '/')} |"
            )
        lines.append("")

    lines.append("## 종목 스코어 · eligibility")
    lines.append("")
    if not data.scores:
        lines.append("_스코어 스냅샷 없음._")
        lines.append("")
    else:
        lines.append("| ticker | total_score | eligibility | weight_input | reason |")
        lines.append("|---|---:|---|---:|---|")
        for s in data.scores:
            elig = "TODO" if s.eligibility is None else str(s.eligibility)
            lines.append(
                f"| {s.ticker} | {s.total_score} | {elig} | {s.weight_input} | "
                f"{s.eligibility_reason.replace('|', '/')} |"
            )
        lines.append("")
        eligible_n = sum(1 for s in data.scores if s.eligibility is True)
        target_n = int(cfg.sizing.target_names)
        if eligible_n < target_n:
            lines.append(
                f"> 적격 종목 부족: eligible={eligible_n} / target_names={target_n} "
                f"(shortfall={target_n - eligible_n}) — 미달 종목 강제 편입 없음."
            )
            lines.append("")

    lines.append(render_performance_hook(cfg, data.fills))

    lines.append("## 스왑 관찰 (observe_only)")
    lines.append("")
    if not data.swap_candidates:
        lines.append("_SWAP_CANDIDATE 없음._")
        lines.append("")
    else:
        lines.append("| held | candidate | held_score | cand_score | gap_pct | hits |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for c in data.swap_candidates:
            lines.append(
                f"| {c.held_ticker} | {c.candidate_ticker} | {c.held_score} | "
                f"{c.candidate_score} | {c.score_gap_pct} | {c.consecutive_hits} |"
            )
        lines.append("")
        lines.append("> 표시만 — 자동 스왑 액션 없음 (`swap_rule.mode=observe_only`).")
        lines.append("")

    lines.append(render_discretionary_section())

    if data.entry.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in data.entry.warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)


def write_status_report(
    cfg: AlphaSystemConfig,
    data: StatusReportInput,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_status_report(cfg, data), encoding="utf-8")
    return path


def print_status_report(cfg: AlphaSystemConfig, data: StatusReportInput) -> str:
    text = render_status_report(cfg, data)
    print(text)
    return text
