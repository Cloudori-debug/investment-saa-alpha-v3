"""Session market for the dual-book screener. One active book at a time."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from alpha_system.screen_book import (
    DEFAULT_MARKET,
    Market,
    market_label,
    normalize_market,
)
from alpha_system.ui.services.approval_chrome import page_tabs
from alpha_system.ui.services.refresh import quant_refresh_when

SESSION_KEY = "screen_market"
_TAB_KEY = "screen_market_tab_ui"
_TAB_LABELS = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}


def sync_market_from_ui() -> Market:
    """Read the 코스피|코스닥 control before load_context.

    Streamlit restores the widget first; SESSION_KEY used to lag by one run,
    so the page showed the other book under the 코스닥 tab.
    """
    picked = st.session_state.get(_TAB_KEY)
    if picked in _TAB_LABELS.values():
        st.session_state[SESSION_KEY] = normalize_market(picked)
    return active_market()


def active_market() -> Market:
    return normalize_market(st.session_state.get(SESSION_KEY, DEFAULT_MARKET))


def set_market(market: object) -> None:
    st.session_state[SESSION_KEY] = normalize_market(market)


def other_market(market: object | None = None) -> Market:
    current = normalize_market(market) if market is not None else active_market()
    return "KOSPI" if current == "KOSDAQ" else "KOSDAQ"


def other_market_caption(root: Path, market: object | None = None) -> str:
    current = normalize_market(market) if market is not None else active_market()
    other = other_market(current)
    when = quant_refresh_when(root, market=other)
    label = market_label(other)
    if when:
        return f"{market_label(current)} 장부 · {label} 정량은 {when}"
    return f"{market_label(current)} 장부 · {label} 정량은 아직 없음"


def render_screen_market_nav(root: Path) -> Market:
    """본문 위 시장 탭. 사이드바 확인 / 포트폴리오는 그대로."""
    current = active_market()
    labels = _TAB_LABELS
    if st.session_state.get(_TAB_KEY) not in labels.values():
        st.session_state[_TAB_KEY] = labels[current]
    picked = page_tabs("시장", ("코스피", "코스닥"), key=_TAB_KEY)
    market = normalize_market(picked)
    if market != current:
        set_market(market)
        st.rerun()
    st.caption(other_market_caption(root, market))
    return market
