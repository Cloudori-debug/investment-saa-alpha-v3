"""
투자 나침반 운용 콘솔 — Streamlit UI
자동매매 없음. 일일 실행·분석·AI보내기는 대시보드에서만.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.compass.profile_options import DEFAULT_PROFILE
from src.settings.user_secrets import apply_secrets_to_env, credential_status
from src.ui.nav_shortcuts import (
    MENU_OPTIONS,
    apply_pending_navigation,
    consume_focus,
    format_menu_sidebar_label,
)
from src.ui.status_banner import render_sidebar_status
from src.ui.styles import inject_app_styles, inject_table_cell_copy

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"

apply_secrets_to_env(DATA_DIR)

st.set_page_config(page_title="투자 나침반", page_icon="🧭", layout="wide")
inject_app_styles()
inject_table_cell_copy()

if "main_menu" not in st.session_state:
    st.session_state["main_menu"] = MENU_OPTIONS[0]

apply_pending_navigation()

with st.sidebar:
    st.title("🧭 투자 나침반")
    st.caption("SAA 코어 · TAA · QVM-SR · **자동매매 없음**")
    render_sidebar_status(DATA_DIR, OUTPUT_DIR)
    st.divider()
    st.markdown("**메뉴**")
    page = st.radio(
        "메뉴",
        MENU_OPTIONS,
        key="main_menu",
        format_func=format_menu_sidebar_label,
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"SAA **{DEFAULT_PROFILE}**")
    st.caption("평일 08:00 자동 분석 (작업 스케줄러)")
    cred = credential_status(DATA_DIR)
    st.caption(f"DART {'✅' if cred['dart'] else '⬜'} · KRX {'✅' if cred['krx'] else '⬜'}")

from src.ui.action_center import render_action_center

render_action_center(DATA_DIR, OUTPUT_DIR)

nav_focus = consume_focus()
profile = DEFAULT_PROFILE

if page == "대시보드":
    from src.ui.dashboard_panel import render_dashboard_page

    render_dashboard_page(DATA_DIR, OUTPUT_DIR)

elif page == "PMI":
    from src.ui.pmi_page import render_pmi_page

    render_pmi_page(DATA_DIR, OUTPUT_DIR)

elif page == "사용법":
    from src.ui.guide_panel import render_guide_page

    render_guide_page(DATA_DIR, OUTPUT_DIR)

elif page == "나침반":
    from src.ui.compass_panel import render_compass_page

    render_compass_page(OUTPUT_DIR)

elif page == "SAA·TAA":
    from src.ui.allocation_panel import render_allocation_page

    render_allocation_page(DATA_DIR, OUTPUT_DIR, profile)

elif page == "알파":
    from src.ui.alpha_panel import render_alpha_page

    render_alpha_page(DATA_DIR, OUTPUT_DIR, focus=nav_focus)

elif page == "종합 포트":
    from src.ui.integrated_portfolio_panel import render_integrated_portfolio_page

    render_integrated_portfolio_page(DATA_DIR, OUTPUT_DIR, focus=nav_focus)

elif page == "백테스트":
    from src.ui.backtest_panel import render_backtest_page

    render_backtest_page(DATA_DIR, OUTPUT_DIR, profile)

elif page == "설정":
    from src.ui.settings_panel import render_settings_page

    render_settings_page(DATA_DIR, focus=nav_focus)
