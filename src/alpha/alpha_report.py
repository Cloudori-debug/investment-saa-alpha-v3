from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.schemas import AlphaCandidate, AlphaPipelineResult, ExcludedRecord, HoldingReview
from src.csv_utils import write_dataframe_csv


def write_alpha_candidates(path: Path, candidates: list[AlphaCandidate]) -> None:
    rows = [c.model_dump() for c in candidates]
    write_dataframe_csv(
        path,
        pd.DataFrame(rows),
        columns=list(AlphaCandidate.model_fields.keys()),
    )


def write_excluded(path: Path, excluded: list[ExcludedRecord]) -> None:
    rows = [e.model_dump() for e in excluded]
    write_dataframe_csv(
        path,
        pd.DataFrame(rows),
        columns=list(ExcludedRecord.model_fields.keys()),
    )


def write_holdings_review(path: Path, reviews: list[HoldingReview]) -> None:
    rows = [r.model_dump() for r in reviews]
    write_dataframe_csv(
        path,
        pd.DataFrame(rows),
        columns=list(HoldingReview.model_fields.keys()),
    )


SCORED_UNIVERSE_COLUMNS = [
    "rank",
    "ticker",
    "name",
    "sector",
    "quality_score",
    "valuation_score",
    "momentum_score",
    "shareholder_return_score",
    "base_score",
    "penalty",
    "total_score",
    "grade",
    "eligible_action",
]


def write_alpha_scored_universe(path: Path, graded: list[dict[str, Any]]) -> None:
    """Persist full scored universe for AI export — scoring logic unchanged."""
    rows = [{col: g.get(col, "") for col in SCORED_UNIVERSE_COLUMNS} for g in graded]
    write_dataframe_csv(path, pd.DataFrame(rows), columns=SCORED_UNIVERSE_COLUMNS)


from src.alpha.portfolio_selector import SelectionResult


def write_alpha_report(
    path: Path,
    result: AlphaPipelineResult,
    *,
    selection: SelectionResult | None = None,
    executable_gate: str | None = None,
    alpha_data_gate: str | None = None,
    execution_scope: str | None = None,
    alpha_trade_permission: str | None = None,
    alpha_position_action: str | None = None,
    gate_notes: list[str] | None = None,
    signal_rows: list | None = None,
    signal_summary: dict[str, Any] | None = None,
    alpha_sector_data_gate: str | None = None,
    top10_candidate_meta: dict[str, Any] | None = None,
    flow_refresh_meta: dict[str, Any] | None = None,
) -> None:
    alpha_gate = alpha_data_gate or result.data_gate
    exec_gate = executable_gate or alpha_gate
    sector_gate = alpha_sector_data_gate or "GREEN"

    lines: list[str] = [
        "# KOSPI Alpha Screener Report",
        "",
        f"**기준일**: {result.as_of}",
        f"**Alpha Data Gate (재무 PIT)**: {alpha_gate}",
        f"**Alpha Sector Data Gate**: {sector_gate}",
        f"**실행 Data Gate**: {exec_gate}",
    ]
    if execution_scope:
        lines.append(f"**Execution Scope**: {execution_scope}")
    if alpha_trade_permission:
        lines.append(f"**Alpha Trade Permission**: {alpha_trade_permission}")
    if alpha_position_action:
        lines.append(f"**Alpha Position Action**: {alpha_position_action}")

    if signal_rows is not None:
        from src.alpha.alpha_signal_board import format_signal_board_report_section, summarize_signal_board

        summary = signal_summary or summarize_signal_board(signal_rows)
        lines.extend(format_signal_board_report_section(signal_rows, summary))

    if top10_candidate_meta:
        from src.alpha.top10_sector_candidate import format_top10_sector_candidate_report_lines

        lines.extend(format_top10_sector_candidate_report_lines(top10_candidate_meta))

    if flow_refresh_meta:
        from src.alpha.flow_refresh import format_flow_coverage_report_lines

        lines.extend(format_flow_coverage_report_lines(flow_refresh_meta))

    if gate_notes:
        lines.extend(["", "### 게이트 메모", ""])
        for note in gate_notes:
            lines.append(f"- {note}")

    lines.extend(["", "## 상위 후보 (QVM 점수 — 실행 상태는 Signal Board 참조)", ""])
    if result.candidates:
        lines.append("| Rank | Ticker | Name | Q | V | M | SR | Total | Grade | Screener Action |")
        lines.append("|------|--------|------|---|---|---|----|-------|-------|-----------------|")
        for c in result.candidates[:15]:
            sr = getattr(c, "shareholder_return_score", 0.0)
            lines.append(
                f"| {c.rank} | {c.ticker} | {c.name} | {c.quality_score:.1f} | "
                f"{c.valuation_score:.1f} | {c.momentum_score:.1f} | {sr:.1f} | {c.total_score:.1f} | "
                f"{c.grade} | {c.eligible_action} |"
            )
    else:
        lines.append("_후보 없음_")

    if selection and selection.proposal:
        lines.extend([
            "",
            "## 포트 제안 (theoretical — watch_only)",
            "",
            "> **Not executable** unless `action_state=Buy-allowed` in `alpha_signal_board.csv` "
            "and `final_execution_decision` permits buy.",
            "",
            "| Rank | Ticker | Role | Sector | Weight% | Grade | Q | V | M | SR |",
            "|------|--------|------|--------|--------:|-------|---:|---:|---:|---:|",
        ])
        for p in selection.proposal:
            lines.append(
                f"| {p.rank} | {p.ticker} | {p.role} | {p.sector} | {p.proposed_weight_pct:.1f} | "
                f"{p.grade} | {p.quality_score:.0f} | {p.valuation_score:.0f} | "
                f"{p.momentum_score:.0f} | {p.shareholder_return_score:.0f} |"
            )

    lines.extend(["", "## 보유·목표 종목 리뷰", ""])
    if result.holdings_review:
        for h in result.holdings_review:
            label = h.review_action
            if label == "REPLACE_CANDIDATE":
                label = "Replace-review (not executable)"
            lines.append(f"- **{h.ticker}** ({h.name}): {label} — {h.reason}")
    else:
        lines.append("_보유종목 없음_")

    lines.extend(["", "## 제외 요약", ""])
    reason_counts: dict[str, int] = {}
    for e in result.excluded:
        reason_counts[e.failed_rule] = reason_counts.get(e.failed_rule, 0) + 1
    for rule, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {rule}: {cnt}건")

    if result.limitations:
        lines.extend(["", "## 데이터 한계", ""])
        for lim in result.limitations:
            lines.append(f"- {lim}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
