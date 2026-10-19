"""Quality-only board for hold/exit edition — Review-only display.

Sorts final proposal by score_q then hakedaka hits. Does not change ranks or target.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from typing import Iterable, Mapping, Optional, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.context import PortfolioRow, ScoreboardRow
from alpha_system.ui.services.rank_watchboard import naver_name_chart_html


@dataclass(frozen=True)
class QualityBoardRow:
    ticker: str
    name: str
    score_q: Optional[float]
    hakedaka_hits: Optional[int]
    hakedaka_detail: str
    total_score: Optional[float]


def score_q_map(scoreboard: Sequence[ScoreboardRow] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for sc in scoreboard or []:
        tk = norm_ticker(getattr(sc, "ticker", None))
        if not tk or sc.score_q is None:
            continue
        try:
            out[tk] = float(sc.score_q)
        except (TypeError, ValueError):
            continue
    return out


def _hits(extra: Mapping[str, object]) -> Optional[int]:
    raw = extra.get("hakedaka_hits")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_quality_rows(
    proposal_rows: Iterable[PortfolioRow],
    *,
    scoreboard: Sequence[ScoreboardRow] | None = None,
    q_by_ticker: Mapping[str, float] | None = None,
) -> list[QualityBoardRow]:
    qmap = dict(q_by_ticker) if q_by_ticker is not None else score_q_map(scoreboard)
    rows: list[QualityBoardRow] = []
    for r in proposal_rows:
        if (r.extra or {}).get("proposal_eligible") is False:
            continue
        tk = norm_ticker(r.ticker)
        if not tk:
            continue
        extra = r.extra or {}
        rows.append(
            QualityBoardRow(
                ticker=tk,
                name=str(r.name or tk),
                score_q=qmap.get(tk),
                hakedaka_hits=_hits(extra),
                hakedaka_detail=str(extra.get("hakedaka_detail") or "").strip(),
                total_score=float(r.total_score) if r.total_score is not None else None,
            )
        )
    rows.sort(
        key=lambda x: (
            x.score_q is None,
            -(x.score_q if x.score_q is not None else 0.0),
            x.hakedaka_hits is None,
            -(x.hakedaka_hits if x.hakedaka_hits is not None else 0),
            x.total_score is None,
            -(x.total_score if x.total_score is not None else 0.0),
            x.ticker,
        )
    )
    return rows


def order_proposal_rows_by_quality(
    rows: Sequence[PortfolioRow],
    *,
    scoreboard: Sequence[ScoreboardRow] | None = None,
    q_by_ticker: Mapping[str, float] | None = None,
) -> list[PortfolioRow]:
    """Display-only: sort eligible proposal rows Q↓·하케다카↓; rank in row.extra."""
    built = build_quality_rows(
        rows, scoreboard=scoreboard, q_by_ticker=q_by_ticker
    )
    by_tk = {
        norm_ticker(r.ticker): r
        for r in rows
        if (r.extra or {}).get("proposal_eligible") is not False
    }
    out: list[PortfolioRow] = []
    seen: set[str] = set()
    for i, qr in enumerate(built, start=1):
        base = by_tk.get(qr.ticker)
        if base is None:
            continue
        seen.add(qr.ticker)
        ex = dict(base.extra or {})
        ex["he_quality_rank"] = i
        if qr.score_q is not None:
            ex["he_score_q"] = qr.score_q
        out.append(replace(base, extra=ex))
    for r in rows:
        tk = norm_ticker(r.ticker)
        if tk in seen or (r.extra or {}).get("proposal_eligible") is False:
            continue
        out.append(r)
    return out


def _fmt_score(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}"


def render_quality_board_html(
    proposal_rows: Iterable[PortfolioRow],
    *,
    scoreboard: Sequence[ScoreboardRow] | None = None,
    q_by_ticker: Mapping[str, float] | None = None,
) -> str:
    items = build_quality_rows(
        proposal_rows, scoreboard=scoreboard, q_by_ticker=q_by_ticker
    )
    parts = [
        '<div class="he-quality-board">',
        '<div class="he-quality-kicker">품질만</div>',
        '<p class="he-quality-note">'
        "최종 제안 중 품질(Q)·하케다카 순 · Review-only · 순위·target 불변"
        "</p>",
    ]
    if not items:
        parts.append(
            '<div class="he-quality-empty">'
            "최종 제안이 없습니다. 컷·게이트·하케다카를 점검하세요."
            "</div>"
        )
        parts.append("</div>")
        return "".join(parts)

    lis: list[str] = []
    for i, row in enumerate(items, start=1):
        hk = row.hakedaka_detail or (
            f"{row.hakedaka_hits}히트" if row.hakedaka_hits is not None else "—"
        )
        lis.append(
            f'<li class="he-quality-item">'
            f'<span class="he-quality-rank">{i}</span>'
            f'<span class="he-quality-name">'
            f"{naver_name_chart_html(row.ticker, row.name)}</span>"
            f'<span class="he-quality-meta">'
            f"Q {_fmt_score(row.score_q)}"
            f" · 하케다카 {escape(hk)}"
            f" · 총점 {_fmt_score(row.total_score)}"
            f"</span></li>"
        )
    parts.append(f'<ol class="he-quality-list">{"".join(lis)}</ol>')
    parts.append("</div>")
    return "".join(parts)
