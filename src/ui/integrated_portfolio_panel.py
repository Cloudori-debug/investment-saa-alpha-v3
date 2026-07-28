from __future__ import annotations



from pathlib import Path



import streamlit as st



from src.ui.export_panel import render_export_page

from src.ui.health_panel import render_health_page

from src.ui.helpers import load_markdown, load_output_csv
from src.ui.table_display import show_trade_actions_table

from src.ui.nav_shortcuts import (

    FOCUS_PORTFOLIO,

    FOCUS_PORTFOLIO_EXPORT,

    FOCUS_PORTFOLIO_GAP,

    FOCUS_PORTFOLIO_HEALTH,

    FOCUS_PORTFOLIO_OPS,

    render_nav_hint,

)

from src.ui.operations_panel import render_operations_page

from src.ui.portfolio_panel import render_portfolio_page

from src.ui.status_banner import render_operational_status





def _render_gap_tab(output_dir: Path) -> None:

    st.caption("종목 Gap 표·편집은 **포트폴리오 (티커)** 탭 · 여기서는 실행 액션만")

    st.info(
        "**Executable** = ETF·현금·채권만 주문 검토. "
        "**Review-only** = kr_alpha 이론값 — 매수·교체·매도 실행 금지."
    )

    trade = load_output_csv(output_dir, "trade_actions.csv")

    if trade is not None:
        show_trade_actions_table(trade, key_prefix="gap_trade", split_review=True)
    else:
        st.info("전체 분석 실행 후 trade_actions.csv 생성")

    theory = load_output_csv(output_dir, "kr_alpha_review_actions.csv")
    if theory is not None and not theory.empty:
        with st.expander("kr_alpha_review_actions.csv (theoretical 원본)"):
            show_trade_actions_table(theory, key_prefix="gap_theory", split_review=False)

    alerts = load_markdown(output_dir, "trigger_alerts.md")

    if alerts:

        st.markdown(alerts)





def render_integrated_portfolio_page(

    data_dir: Path,

    output_dir: Path,

    *,

    focus: str | None = None,

) -> None:

    st.header("📁 종합 포트")

    st.caption(

        "**유일한 종목·Gap 진실 공급원** — 실제 보유 vs TAA 반영 목표 · "

        "자산군 %는 **SAA·TAA** 메뉴 배분 흐름 참고"

    )

    render_operational_status(data_dir, output_dir)

    render_nav_hint(focus)



    if focus == FOCUS_PORTFOLIO:

        with st.container(border=True):

            st.subheader("📍 포트폴리오 (티커)")

            render_portfolio_page(data_dir, output_dir)

        st.divider()

    elif focus == FOCUS_PORTFOLIO_GAP:

        with st.container(border=True):

            st.subheader("📍 Gap·실행")

            _render_gap_tab(output_dir)

        st.divider()

    elif focus == FOCUS_PORTFOLIO_OPS:

        with st.container(border=True):

            st.subheader("📍 운용승인")

            render_operations_page(data_dir, output_dir)

        st.divider()

    elif focus == FOCUS_PORTFOLIO_EXPORT:

        with st.container(border=True):

            st.subheader("📍 AI보내기")

            render_export_page(data_dir, output_dir)

        st.divider()

    elif focus == FOCUS_PORTFOLIO_HEALTH:

        with st.container(border=True):

            st.subheader("📍 검증")

            render_health_page(data_dir, output_dir)

        st.divider()



    tab_port, tab_gap, tab_ops, tab_export, tab_health = st.tabs(

        ["포트폴리오 (티커)", "Gap·실행", "운용승인", "AI보내기", "검증"]

    )



    with tab_port:

        if focus != FOCUS_PORTFOLIO:

            render_portfolio_page(data_dir, output_dir)



    with tab_gap:

        if focus != FOCUS_PORTFOLIO_GAP:

            _render_gap_tab(output_dir)



    with tab_ops:

        if focus != FOCUS_PORTFOLIO_OPS:

            render_operations_page(data_dir, output_dir)



    with tab_export:

        if focus != FOCUS_PORTFOLIO_EXPORT:

            render_export_page(data_dir, output_dir)



    with tab_health:

        if focus != FOCUS_PORTFOLIO_HEALTH:

            render_health_page(data_dir, output_dir)


