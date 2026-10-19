"""Portfolio page — hold/exit Review edition overlay."""

from __future__ import annotations

import streamlit as st

from alpha_system.hold_exit_review.monthly_board import render_monthly_review_html
from alpha_system.hold_exit_review.quality_board import order_proposal_rows_by_quality
from alpha_system.hold_exit_review.styles import hold_exit_edition_css
from alpha_system.hold_exit_review.widgets import row_main_html as hold_exit_row_main_html
from alpha_system.ui.pages import portfolio as portfolio_base
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services import portfolio_widgets as pw


def render_portfolio_hold_exit(ctx: DashboardContext) -> None:
    meta = getattr(ctx, "extra_hold_exit", None) or {}
    label = str(meta.get("edition_label") or "보유·매도 Review v1")
    st.markdown(
        f"<style>{hold_exit_edition_css()}</style>"
        f'<div class="he-edition-banner">'
        f"<strong>{label}</strong>"
        f'<div class="he-edition-chips">'
        f'<span class="he-edition-chip">점수 매주</span>'
        f'<span class="he-edition-chip">매매 월말 Review</span>'
        f'<span class="he-edition-chip">±10% 규칙 없음</span>'
        f'<span class="he-edition-chip">target·순위 불변</span>'
        f"</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        render_monthly_review_html(list(ctx.ops_portfolio_rows or [])),
        unsafe_allow_html=True,
    )

    original = pw._row_main_html
    pw._row_main_html = hold_exit_row_main_html
    def _sort_proposal(
        eligible: list,
        c: DashboardContext,
    ) -> list:
        return order_proposal_rows_by_quality(
            eligible,
            scoreboard=list(c.scoreboard_rows or []),
        )

    try:
        portfolio_base.render_portfolio(
            ctx,
            proposal_eligible_sorter=_sort_proposal,
            proposal_final_sort_label="품질 Q↓·하케다카↓",
        )
    finally:
        pw._row_main_html = original
