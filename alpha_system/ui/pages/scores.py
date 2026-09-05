"""Score board — CECS shortlist."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.services.approval_chrome import ap_copy
from alpha_system.ui.services.context import DashboardContext, ScoreboardRow
from alpha_system.ui.services.device import is_mobile_browser


def _elig_label(value: bool | None) -> str:
    if value is True:
        return "예"
    if value is False:
        return "아니오"
    return "—"


def _status_label(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw == "final":
        return "확정"
    if raw == "draft":
        return "초안"
    return value or "—"


def _row_name(row: ScoreboardRow) -> str:
    return f"{row.name}({row.ticker})" if row.name else row.ticker


def render_scores(ctx: DashboardContext) -> None:
    cutoff = ctx.cfg.scoring.score_cutoff
    if cutoff is None:
        st.caption(ap_copy("quant_cutoff_open"))
    else:
        st.caption(ap_copy("quant_cutoff", cutoff=cutoff))
    min_q = getattr(ctx.cfg.scoring, "quality_min_score", None)
    if min_q is not None:
        st.caption(f"품질 하한 {min_q:g} · ROE 없으면 적격 아님")

    rows = ctx.scoreboard_rows
    if not rows:
        st.info(ap_copy("quant_empty"))
        return

    use_mobile = is_mobile_browser()
    if use_mobile:
        data = [
            {
                "종목": row.name or row.ticker,
                "합계": row.total_score,
                "적격": _elig_label(row.eligibility),
                "보유": "●" if row.is_held else "",
            }
            for row in rows
        ]
    else:
        data = [
            {
                "코드": row.ticker,
                "종목": row.name,
                "합계": row.total_score,
                "품질": row.score_q,
                "가치": row.score_v,
                "환원": row.score_sr,
                "리스크": row.score_r,
                "CECS(참고)": row.cecs,
                "적격": _elig_label(row.eligibility),
                "섹터대체": "예" if row.sector_peer_fallback else "",
                "보유": "●" if row.is_held else "",
                "상태": _status_label(row.status),
            }
            for row in rows
        ]

    st.dataframe(data, use_container_width=True, hide_index=True)

    if cutoff is not None:
        below_held = [
            row
            for row in rows
            if row.is_held and row.total_score is not None and row.total_score < cutoff
        ]
        below = [
            row for row in rows if row.total_score is not None and row.total_score < cutoff
        ]
        if below:
            st.caption(ap_copy("quant_below", n=len(below)))
        if below_held:
            names = ", ".join(_row_name(row) for row in below_held)
            st.warning(ap_copy("quant_below_held", names=names))
