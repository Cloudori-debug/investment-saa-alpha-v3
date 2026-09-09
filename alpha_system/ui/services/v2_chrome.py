"""v2 shell chrome — sidebar main menu + slim header (ops assistant IA)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import streamlit as st

from alpha_system.product import PRODUCT_NAME, PRODUCT_TAGLINE
from alpha_system.ui.services.app_version import sidebar_version_label
from alpha_system.ui.services.nav import (
    NAV_MAIN_PAGES,
    NAV_MORE_PAGES,
    PAGE_APPROVAL,
    PAGE_HINTS,
    page_display_name,
)
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.theme_prefs import (
    THEME_DARK,
    THEME_LIGHT,
    load_ui_theme,
    save_ui_theme,
    theme_label,
)


def render_theme_picker(
    root: Path,
    *,
    key: str,
    compact: bool = False,
) -> None:
    """Persist dark/light. Compact = sidebar; full = 설정 → 화면."""
    options = (
        copy_get("display", "theme_dark", default="다크"),
        copy_get("display", "theme_light", default="일반"),
    )
    if key not in st.session_state:
        st.session_state[key] = theme_label(load_ui_theme(root))

    def _persist() -> None:
        picked = str(st.session_state.get(key) or "")
        theme = THEME_DARK if picked == options[0] else THEME_LIGHT
        save_ui_theme(root, theme)
        st.session_state["saa_ui_theme"] = theme
        other = (
            "saa_theme_settings" if key == "saa_theme_sidebar" else "saa_theme_sidebar"
        )
        st.session_state[other] = theme_label(theme)

    label = copy_get("display", "theme_label", default="화면 테마")
    st.radio(
        label,
        options,
        horizontal=True,
        key=key,
        on_change=_persist,
        label_visibility="collapsed" if compact else "visible",
    )
    if compact:
        st.caption(copy_get("display", "sidebar_caption", default="화면"))


def render_primary_nav(
    pages: Sequence[str],
    *,
    key: str = "alpha_page",
    approval_badge: int | None = None,
) -> str:
    """Sidebar: 확인 / 포트폴리오 + 더보기."""
    options = list(pages)
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    current = str(st.session_state[key])

    ver = sidebar_version_label()
    st.markdown(
        '<div class="v2-side-nav-brand">'
        f'<div class="v2-side-nav-title">{PRODUCT_NAME}</div>'
        f'<div class="v2-side-nav-sub">{PRODUCT_TAGLINE}</div>'
        f'<div class="v2-side-nav-ver">{ver}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="v2-side-nav-label">메뉴</div>',
        unsafe_allow_html=True,
    )

    main_pages = [p for p in NAV_MAIN_PAGES if p in options]
    more_pages = [p for p in NAV_MORE_PAGES if p in options]
    for page in options:
        if page not in main_pages and page not in more_pages:
            more_pages.append(page)

    # Stable ASCII keys so label renames (보유→포트폴리오) do not stick on old widgets.
    _btn_ids = {
        "홈": "home",
        "결재함": "approval",
        "포트폴리오": "portfolio",
        "경제시그널": "economy",
        "저널": "journal",
        "레짐": "regime",
        "설정": "settings",
    }

    def _nav_button(page: str) -> None:
        is_active = current == page
        title = page_display_name(
            page,
            badge=approval_badge if page == PAGE_APPROVAL else None,
        )
        hint = PAGE_HINTS.get(page, "")
        btn_id = _btn_ids.get(page, "page")
        if st.button(
            title,
            key=f"_saa_nav_{btn_id}_v3",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            if not is_active:
                st.session_state[key] = page
                st.rerun()
        if hint:
            st.markdown(
                f'<div class="v2-nav-card-hint">{hint}</div>',
                unsafe_allow_html=True,
            )

    for page in main_pages:
        _nav_button(page)

    more_active = current in more_pages
    with st.expander("더보기", expanded=more_active):
        st.caption("경제 시그널 · 저널 · 화면/API/백업")
        for page in more_pages:
            _nav_button(page)

    return str(st.session_state.get(key) or options[0])


def render_app_header(*, as_of: str | None = None, page: str | None = None) -> None:
    """Date stamp only — page identity lives in page_head on each menu."""
    del page
    if not as_of:
        return
    st.markdown(
        f"""
<div class="v2-shell-header v2-shell-header-slim">
  <span class="v2-asof">as_of {as_of}</span>
</div>
""",
        unsafe_allow_html=True,
    )
