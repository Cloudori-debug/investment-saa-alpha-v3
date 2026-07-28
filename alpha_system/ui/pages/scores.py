"""Score board — CECS shortlist."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.services.context import DashboardContext


def render_scores(ctx: DashboardContext) -> None:
    cutoff = ctx.cfg.scoring.score_cutoff
    if cutoff is None:
        st.markdown(
            '<div class="alpha-muted-note">컷오프 미확정 — 자격 판정 전. 정렬만 표시합니다.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(f"컷라인: {cutoff}")

    rows = ctx.scoreboard_rows
    if not rows:
        st.info("채점 데이터가 없습니다. `data/cecs_manual_scoring_template.csv` 를 확인하세요.")
        return

    # compact = phone; otherwise PC full columns
    use_mobile = bool(st.session_state.get("compact_mode", False))
    if use_mobile:
        data = [
            {
                "종목": f"{r.name}",
                "total": r.total_score,
                "elig": "Y" if r.eligibility else ("?" if r.eligibility is None else "N"),
                "보유": "●" if r.is_held else "",
            }
            for r in rows
        ]
    else:
        data = [
            {
                "ticker": r.ticker,
                "name": r.name,
                "total": r.total_score,
                "Q": r.score_q,
                "V": r.score_v,
                "SR": r.score_sr,
                "R": r.score_r,
                "cecs": r.cecs,
                "elig": r.eligibility,
                "fallback": r.sector_peer_fallback,
                "held": r.is_held,
                "status": r.status,
            }
            for r in rows
        ]

    st.dataframe(data, use_container_width=True, hide_index=True)

    if cutoff is not None:
        below_held = [
            r
            for r in rows
            if r.is_held and r.total_score is not None and r.total_score < cutoff
        ]
        below = [r for r in rows if r.total_score is not None and r.total_score < cutoff]
        if below:
            st.markdown("---")
            st.caption(f"컷라인 미달 {len(below)}종")
        if below_held:
            st.warning(
                "컷라인 미달 보유: "
                + ", ".join(f"{r.name}({r.ticker})" for r in below_held)
                + " — exit 연동 예고"
            )
