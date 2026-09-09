"""Proposal daily-chart refresh — Review-only. Rows show the readout."""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from alpha_system.proposal_chart import ChartRead, load_cached_charts, norm_ticker, refresh_proposal_charts
from alpha_system.screen_book import market_label, normalize_market
from alpha_system.ui.services.context import DashboardContext, PortfolioRow
from alpha_system.ui.services.ui_copy import copy_get


def reads_by_ticker(ctx: DashboardContext) -> dict[str, ChartRead]:
    market = normalize_market(getattr(ctx, "screen_market", None) or "KOSPI")
    board = load_cached_charts(ctx.root, market)
    if board is None:
        return {}
    return {norm_ticker(item.ticker): item for item in board.items if norm_ticker(item.ticker)}


def render_proposal_chart_refresh(ctx: DashboardContext, rows: Sequence[PortfolioRow]) -> None:
    eligible = [r for r in rows if norm_ticker(r.ticker)]
    if not eligible:
        return
    market = normalize_market(getattr(ctx, "screen_market", None) or "KOSPI")
    label = market_label(market)
    clicked = st.button(
        copy_get("portfolio", "chart_read_refresh", default="{market} 일봉 읽기", market=label),
        key=f"proposal_chart_refresh_{market}",
    )
    if clicked:
        names = [{"ticker": norm_ticker(r.ticker), "name": r.name} for r in eligible]
        try:
            with st.spinner("일봉 받는 중… 종목당 잠깐 걸립니다."):
                refresh_proposal_charts(ctx.root, names, market=market)
        except Exception as exc:
            st.error(str(exc)[:240])
        else:
            st.rerun()
    cached = reads_by_ticker(ctx)
    wanted = {norm_ticker(r.ticker) for r in eligible}
    if not any(tk in cached for tk in wanted):
        st.caption(
            copy_get(
                "portfolio",
                "chart_read_empty",
                default="이 장부에서 「일봉 읽기」를 누르면 종목 이름 아래에 분석이 붙습니다. 코스피·코스닥은 각각 한 번입니다.",
            )
        )
