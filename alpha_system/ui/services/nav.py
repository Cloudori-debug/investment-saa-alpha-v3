"""Dashboard navigation — pending page switch + focus/prefill (widget-safe)."""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

# Canonical page labels (radio keys) — review/approval-only surface
PAGE_APPROVAL = "결재함"
PAGE_PORTFOLIO = "포트폴리오"
PAGE_ECONOMY = "경제시그널"
PAGE_JOURNAL = "저널"
PAGE_SETTINGS = "설정"
PAGE_HOME = PAGE_APPROVAL  # removed from IA; old session keys land on 확인
PAGE_REGIME = PAGE_APPROVAL  # removed from IA

# Legacy aliases kept so older navigate() call sites keep working.
PAGE_EVENTS = PAGE_APPROVAL
PAGE_SCORES = PAGE_APPROVAL
PAGE_RULES = PAGE_APPROVAL
PAGE_CECS = PAGE_APPROVAL

# Sellable IA order: 확인 → 포트폴리오 → 경제 시그널; 저널·설정 in 더보기.
PRIMARY_PAGES = (
    PAGE_APPROVAL,
    PAGE_PORTFOLIO,
    PAGE_ECONOMY,
    PAGE_JOURNAL,
    PAGE_SETTINGS,
)

# One-line hints under sidebar main menu (product UI).
PAGE_HINTS: dict[str, str] = {
    PAGE_APPROVAL: "정량 · 정성",
    PAGE_PORTFOLIO: "관찰 · 제안 · 실보유",
    PAGE_ECONOMY: "나침반 · 슬리브 Review",
    PAGE_JOURNAL: "판정·승인 기록",
    PAGE_SETTINGS: "화면 · API · 도구",
}

# Sidebar display names (internal page keys unchanged).
PAGE_DISPLAY_NAMES: dict[str, str] = {
    PAGE_APPROVAL: "확인",
    PAGE_PORTFOLIO: "포트폴리오",
    PAGE_ECONOMY: "경제 나침반",
    PAGE_JOURNAL: "저널",
    PAGE_SETTINGS: "설정",
}

# Primary strip vs folded "더보기".
NAV_MAIN_PAGES: tuple[str, ...] = (PAGE_APPROVAL, PAGE_PORTFOLIO, PAGE_ECONOMY)
NAV_MORE_PAGES: tuple[str, ...] = (PAGE_JOURNAL, PAGE_SETTINGS)


def page_display_name(page: str, *, badge: int | None = None) -> str:
    label = PAGE_DISPLAY_NAMES.get(page, page)
    if page == PAGE_APPROVAL and badge:
        return f"{label} · {badge}"
    return label


ALL_PAGES = PRIMARY_PAGES

# Old radio labels that may still sit in session_state
_LEGACY_PAGE_REDIRECT = {
    "이벤트 입력": PAGE_APPROVAL,
    "설정·이벤트": PAGE_APPROVAL,
    "CECS 채점": PAGE_PORTFOLIO,
    "규칙": PAGE_APPROVAL,
    "스코어": PAGE_APPROVAL,
    "홈": PAGE_APPROVAL,
    "레짐": PAGE_APPROVAL,
}

FOCUS_T2 = "t2_event"
FOCUS_DATA_REFRESH = "data_refresh"
FOCUS_T3_DETAIL = "t3_detail"
FOCUS_GO_LIVE = "go_live"
FOCUS_WEEKLY_QUAL = "weekly_qual"
FOCUS_MONTHLY_CECS = "monthly_cecs"
FOCUS_JOURNAL_DISC = "journal_discretionary"
FOCUS_RULES_PREFIX = "rules_"  # rules_T1 …
FOCUS_CECS_SCORE = "cecs_score"
FOCUS_SCORES = "scores_review"
FOCUS_SETTINGS_API = "settings_api"
FOCUS_SETTINGS_DATA = "settings_data"
FOCUS_HOLDINGS_INPUT = "holdings_input"


def navigate(
    page: str,
    *,
    focus: Optional[str] = None,
    prefill: Optional[dict[str, Any]] = None,
) -> None:
    """Queue page change before next radio instantiate; then rerun."""
    page = _LEGACY_PAGE_REDIRECT.get(page, page)
    if page not in ALL_PAGES:
        raise ValueError(f"unknown page: {page}")
    st.session_state["pending_alpha_page"] = page
    if focus is not None:
        st.session_state["nav_focus"] = focus
    if prefill:
        for key, value in prefill.items():
            st.session_state[f"nav_prefill_{key}"] = value
    st.rerun()


def consume_focus() -> Optional[str]:
    return st.session_state.pop("nav_focus", None)


def peek_focus() -> Optional[str]:
    return st.session_state.get("nav_focus")


def pop_prefill(key: str, default: Any = None) -> Any:
    return st.session_state.pop(f"nav_prefill_{key}", default)


def get_prefill(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"nav_prefill_{key}", default)


def normalize_page_label(page: str | None) -> str:
    if not page:
        return PAGE_APPROVAL
    return _LEGACY_PAGE_REDIRECT.get(page, page)


def apply_pending_page() -> None:
    pending = st.session_state.pop("pending_alpha_page", None)
    if pending is not None:
        pending = normalize_page_label(pending)
        if pending in ALL_PAGES:
            st.session_state["alpha_page"] = pending
    current = normalize_page_label(st.session_state.get("alpha_page"))
    if current not in ALL_PAGES:
        current = PAGE_APPROVAL
    st.session_state["alpha_page"] = current
