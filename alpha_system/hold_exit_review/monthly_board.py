"""Monthly Review board HTML — edition only."""

from __future__ import annotations

from html import escape
from typing import Iterable

from alpha_system.ui.services.context import PortfolioRow


def _rows_by_state(rows: Iterable[PortfolioRow], state: str) -> list[PortfolioRow]:
    return [
        r
        for r in rows
        if str((r.extra or {}).get("hold_exit_state") or "") == state
    ]


def _card(title: str, items: list[PortfolioRow], empty: str, *, tone: str) -> str:
    if not items:
        body = f'<div class="he-month-empty">{escape(empty)}</div>'
    else:
        chips = "".join(
            f'<div class="he-month-chip">'
            f'<span class="he-month-name">{escape(r.name)}</span>'
            f'<span class="he-month-why">'
            f"{escape(str((r.extra or {}).get('hold_exit_why') or r.ops_signal_label or '—'))}"
            f"</span></div>"
            for r in items
        )
        body = f'<div class="he-month-chips">{chips}</div>'
    return (
        f'<div class="he-month-card he-month-{escape(tone)}">'
        f'<div class="he-month-card-h">'
        f'<span class="he-month-title">{escape(title)}</span>'
        f'<span class="he-month-count">{len(items)}</span>'
        f"</div>"
        f"{body}</div>"
    )


def render_monthly_review_html(ops_rows: list[PortfolioRow]) -> str:
    dropped = _rows_by_state(ops_rows, "just_dropped")
    rotate = _rows_by_state(ops_rows, "rotate_review")
    cap = _rows_by_state(ops_rows, "cap_trim")
    thesis = _rows_by_state(ops_rows, "thesis_review")
    watch = _rows_by_state(ops_rows, "watch")

    parts = [
        '<div class="he-month-board">',
        '<div class="he-month-kicker">월말 매매 Review</div>',
        '<p class="he-month-note">'
        "제안 이탈은 <strong>같은 주</strong>에 알림 · 4주는 교체 결정 유예 · "
        "자동 주문·target 변경 없음"
        "</p>",
        '<div class="he-month-grid">',
        _card("이번 주 제안 이탈", dropped, "해당 없음", tone="hot"),
        _card("교체 검토", rotate, "해당 없음", tone="warn"),
        _card("비중 초과", cap, "해당 없음", tone="warn"),
        _card("가설·즉시 검토", thesis, "해당 없음", tone="warn"),
        _card("관찰(제안 밖)", watch, "해당 없음", tone="muted"),
        "</div></div>",
    ]
    return "".join(parts)
