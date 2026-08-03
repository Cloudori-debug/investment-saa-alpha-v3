"""
SAA 알파 v3 대시보드 — Streamlit 단일 앱 (모바일 우선).

실행 (반드시 v3 폴더에서):
  cd C:\\Cursor\\investment-saa-alpha-v3
  streamlit run alpha_dashboard.py --server.address 127.0.0.1 --server.port 8501

일상 진입: 투자나침반.bat  /  Start-Ops-Assistant.vbs
코드 루트: investment-saa-alpha-v3 only (v1/v2 폴더 없음)
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from alpha_system.ui.pages import approval, home, journal, portfolio, regime, settings
from alpha_system.ui.services.context import load_context
from alpha_system.ui.services.nav import (
    PAGE_APPROVAL,
    PAGE_HOME,
    PAGE_JOURNAL,
    PAGE_PORTFOLIO,
    PAGE_REGIME,
    PAGE_SETTINGS,
    PRIMARY_PAGES,
    apply_pending_page,
    normalize_page_label,
)
from alpha_system.ui.services.proposal_freeze import is_freeze_active, load_freeze
from alpha_system.ui.services.v2_chrome import render_app_header, render_primary_nav
from alpha_system.ui.styles import inject_dashboard_styles

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="SAA 알파 운용 비서",
    page_icon="📗",
    layout="wide",
    initial_sidebar_state="auto",
)

if "compact_mode" not in st.session_state:
    st.session_state["compact_mode"] = False
if "alpha_page" not in st.session_state:
    st.session_state["alpha_page"] = PAGE_HOME
else:
    st.session_state["alpha_page"] = normalize_page_label(
        st.session_state.get("alpha_page")
    )

apply_pending_page()

inject_dashboard_styles(compact=bool(st.session_state.get("compact_mode")))

PAGES = {
    PAGE_HOME: home.render_home,
    PAGE_APPROVAL: approval.render_approval,
    PAGE_PORTFOLIO: portfolio.render_portfolio,
    PAGE_JOURNAL: journal.render_journal,
    PAGE_REGIME: regime.render_regime,
    PAGE_SETTINGS: settings.render_settings,
}

try:
    ctx = load_context(ROOT)
except Exception as exc:
    st.error(f"컨텍스트 로드 실패: {exc}")
    st.stop()

_waiting = 0
try:
    from alpha_system.ui.services.v2_chrome import _count_waiting_targets

    _waiting = int(_count_waiting_targets(ctx))
except Exception:
    _waiting = 0

with st.sidebar:
    page = render_primary_nav(
        PRIMARY_PAGES,
        approval_badge=_waiting if _waiting else None,
    )
    st.markdown("---")
    st.toggle(
        "컴팩트 모드 (모바일 1열)",
        key="compact_mode",
        help="켜면 본문 폭을 좁혀 모바일 1열 레이아웃을 강제합니다.",
    )
    if is_freeze_active(ROOT):
        fr = load_freeze(ROOT)
        st.caption(
            f"제안 스냅샷 고정 · {fr.as_of or '—'} · {len(fr.tickers)}종"
        )

# Shell: sidebar = brand+nav only. No legacy ops strip / dual brand header.
render_app_header(as_of=ctx.as_of.isoformat(), page=page)
PAGES[page](ctx)

st.caption(
    "순위=정량(Ops A) · 정성=선택 공적 브레이크 · "
    "증권사 SoT 금지 · target_portfolio 자동 변경 없음 · 매매는 증권사"
)
