"""
알파 스크리너 — 보유·매도 Review 에디션 (병렬 실행).

기본 앱(alpha_dashboard.py)은 그대로 두고, 전체 hold/exit 스펙을 이 진입점에서만 켭니다.

  streamlit run alpha_dashboard_hold_exit.py --server.address 127.0.0.1 --server.port 8502
"""

from __future__ import annotations

from pathlib import Path
import sys

try:
    from alpha_system.win_sac_pyarrow import shield_pandas_from_blocked_compute
except KeyError:
    for _key in list(sys.modules):
        if _key == "alpha_system" or _key.startswith("alpha_system."):
            sys.modules.pop(_key, None)
    from alpha_system.win_sac_pyarrow import shield_pandas_from_blocked_compute

shield_pandas_from_blocked_compute()

import streamlit as st

from alpha_system.win_sac_pyarrow import install_streamlit_dataframe_fallback

install_streamlit_dataframe_fallback()

from alpha_system.hold_exit_review.context_loader import load_context_hold_exit
from alpha_system.ui.pages import approval, economy, journal, settings
from alpha_system.ui.pages import portfolio_hold_exit
from alpha_system.ui.services.job_sidebar import render_job_sidebar
from alpha_system.ui.services.screen_market import sync_market_from_ui
from alpha_system.ui.services.screen_horizon import sync_horizon_from_ui
from alpha_system.ui.services.nav import (
    PAGE_APPROVAL,
    PAGE_ECONOMY,
    PAGE_JOURNAL,
    PAGE_PORTFOLIO,
    PAGE_SETTINGS,
    PRIMARY_PAGES,
    apply_pending_page,
    normalize_page_label,
)
from alpha_system.ui.services.proposal_freeze import is_freeze_active, load_freeze
from alpha_system.ui.services.v2_chrome import (
    render_app_header,
    render_primary_nav,
    render_theme_picker,
)
from alpha_system.ui.services.operator_errors import render_operator_exception, safe_page
from alpha_system.ui.styles import inject_dashboard_styles
from alpha_system.ui.theme_prefs import load_ui_theme, theme_label

ROOT = Path(__file__).resolve().parent
EDITION_NAME = "알파 스크리너 · 보유·매도 Review"

st.set_page_config(
    page_title=EDITION_NAME,
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "alpha_page" not in st.session_state:
    st.session_state["alpha_page"] = PAGE_APPROVAL
else:
    st.session_state["alpha_page"] = normalize_page_label(
        st.session_state.get("alpha_page")
    )

apply_pending_page()

st.session_state["_dashboard_root"] = str(ROOT)
_theme_label = theme_label(load_ui_theme(ROOT))
if "saa_theme_sidebar" not in st.session_state:
    st.session_state["saa_theme_sidebar"] = _theme_label
if "saa_theme_settings" not in st.session_state:
    st.session_state["saa_theme_settings"] = _theme_label
inject_dashboard_styles(ROOT)

PAGES = {
    PAGE_APPROVAL: approval.render_approval,
    PAGE_PORTFOLIO: portfolio_hold_exit.render_portfolio_hold_exit,
    PAGE_ECONOMY: economy.render_economy,
    PAGE_JOURNAL: journal.render_journal,
    PAGE_SETTINGS: settings.render_settings,
}

try:
    ctx = load_context_hold_exit(
        ROOT,
        market=sync_market_from_ui(),
        horizon=sync_horizon_from_ui(),
    )
except Exception as exc:
    render_operator_exception(exc)
    st.stop()

with st.sidebar:
    page = render_primary_nav(PRIMARY_PAGES)
    render_theme_picker(ROOT, key="saa_theme_sidebar", compact=True)
    st.caption("에디션: 보유·매도 Review v1")
    st.markdown("---")
    render_job_sidebar()
    if is_freeze_active(ROOT):
        fr = load_freeze(ROOT)
        st.caption(f"제안 스냅샷 고정 · {fr.as_of or '—'} · {len(fr.tickers)}종")

render_app_header(as_of=ctx.as_of.isoformat(), page=page)
safe_page(PAGES[page], ctx)

st.caption(
    "Review-only · 히스테리시스·월말 교체 보드 · 기본 대시보드(8501)와 데이터 공유 · "
    "target_portfolio 자동 변경 없음"
)
