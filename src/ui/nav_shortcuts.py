"""Streamlit 메뉴·하위 탭 바로가기."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

MENU_OPTIONS: list[str] = [
    "대시보드",
    "PMI",
    "사용법",
    "나침반",
    "SAA·TAA",
    "알파",
    "종합 포트",
    "백테스트",
    "설정",
]

MENU_SIDEBAR_LABELS: dict[str, str] = {
    "대시보드": "🏠 대시보드",
    "PMI": "📊 PMI",
    "사용법": "📖 사용법",
    "나침반": "🧭 나침반",
    "SAA·TAA": "📐 SAA·TAA",
    "알파": "🔬 알파",
    "종합 포트": "📁 종합 포트",
    "백테스트": "📈 백테스트",
    "설정": "⚙️ 설정",
}


def format_menu_sidebar_label(menu: str) -> str:
    return MENU_SIDEBAR_LABELS.get(menu, menu)

# 하위 포커스 키 — 각 패널 render_*(..., focus=) 와 대응
FOCUS_SETTINGS_DATA = "settings_data"
FOCUS_SETTINGS_API = "settings_api"
FOCUS_PORTFOLIO = "portfolio"
FOCUS_PORTFOLIO_GAP = "portfolio_gap"
FOCUS_PORTFOLIO_OPS = "portfolio_ops"
FOCUS_PORTFOLIO_EXPORT = "portfolio_export"
FOCUS_PORTFOLIO_HEALTH = "portfolio_health"
FOCUS_ALPHA_TARGET = "alpha_target"
FOCUS_ALPHA_REVIEW = "alpha_review"

# 알파 페이지 하위 탭 — render_alpha_page radio 와 동기화
ALPHA_SUB_TAB_KEYS: tuple[str, ...] = (
    "shortlist",
    "proposal",
    "review",
    "target",
    "hakedaka",
    "report",
    "flow",
)
ALPHA_SUB_TAB_LABELS: tuple[str, ...] = (
    "숏리스트·축별",
    "포트 제안",
    "보유 리뷰",
    "Target 승인",
    "하케다카 50",
    "리포트",
    "수급 현황",
)
FOCUS_TO_ALPHA_SUB_TAB: dict[str, str] = {
    FOCUS_ALPHA_TARGET: "target",
    FOCUS_ALPHA_REVIEW: "review",
}


@dataclass(frozen=True)
class NavShortcut:
    label: str
    menu: str
    focus: str | None = None
    help_text: str = ""


def apply_pending_navigation() -> None:
    """radio 위젯 생성 전에 호출 — pending 메뉴를 main_menu에 반영."""
    pending = st.session_state.pop("_pending_menu", None)
    if pending and pending in MENU_OPTIONS:
        st.session_state["main_menu"] = pending


def navigate(menu: str, *, focus: str | None = None) -> None:
    if menu not in MENU_OPTIONS:
        raise ValueError(f"unknown menu: {menu}")
    st.session_state["_pending_menu"] = menu
    st.session_state["nav_focus"] = focus or ""
    if menu == "알파" and focus in FOCUS_TO_ALPHA_SUB_TAB:
        st.session_state["alpha_sub_tab_key"] = FOCUS_TO_ALPHA_SUB_TAB[focus]
    st.rerun()


def consume_focus() -> str | None:
    focus = st.session_state.pop("nav_focus", "") or ""
    return focus or None


def shortcut_button(
    shortcut: NavShortcut,
    *,
    key: str,
    use_container_width: bool = True,
    type: str = "secondary",
) -> None:
    if st.button(
        shortcut.label,
        key=key,
        use_container_width=use_container_width,
        type=type,  # type: ignore[arg-type]
        help=shortcut.help_text or None,
    ):
        navigate(shortcut.menu, focus=shortcut.focus)


def render_shortcut_row(shortcuts: list[NavShortcut], *, key_prefix: str, columns: int | None = None) -> None:
    if not shortcuts:
        return
    n = columns or min(len(shortcuts), 4)
    cols = st.columns(n)
    for i, sc in enumerate(shortcuts):
        with cols[i % n]:
            shortcut_button(sc, key=f"{key_prefix}_{sc.menu}_{sc.focus or 'root'}_{i}")


def render_nav_hint(focus: str | None) -> None:
    hints = {
        FOCUS_SETTINGS_DATA: "👉 **설정 → 데이터** 탭에서 시장지표·positions·수집을 확인하세요.",
        FOCUS_SETTINGS_API: "👉 **설정 → API 키** 탭에서 DART/KRX 자격을 확인하세요.",
        FOCUS_PORTFOLIO: "👉 **포트폴리오 (티커)** 탭에서 보유·Gap·positions 저장.",
        FOCUS_PORTFOLIO_GAP: "👉 **Gap·실행** 탭에서 trade_actions·트리거 알림 확인.",
        FOCUS_PORTFOLIO_OPS: "👉 **운용승인** 탭에서 AC·Execution Scope 확인.",
        FOCUS_PORTFOLIO_EXPORT: "👉 **AI보내기** 탭에서 번들 미리보기·ZIP.",
        FOCUS_PORTFOLIO_HEALTH: "👉 **검증** 탭에서 system_health 확인.",
        FOCUS_ALPHA_TARGET: "👉 아래 **Target 승인** 탭에서 diff·비중 확인 후 승인하세요.",
        FOCUS_ALPHA_REVIEW: "👉 **보유 리뷰** 탭에서 TRIM/REPLACE 검토.",
    }
    if focus and focus in hints:
        st.info(hints[focus])


# --- 사전 정의 바로가기 ---

SHORTCUT_SETTINGS_DATA = NavShortcut(
    "⚙️ 설정 · 데이터",
    "설정",
    FOCUS_SETTINGS_DATA,
    "시장지표·positions·PyKRX 갱신",
)
SHORTCUT_SETTINGS_API = NavShortcut(
    "🔑 API 키",
    "설정",
    FOCUS_SETTINGS_API,
    "DART/KRX 자격",
)
SHORTCUT_COMPASS = NavShortcut("🧭 나침반", "나침반", help_text="레짐·Data Gate·4축")
SHORTCUT_SAA = NavShortcut("📐 SAA·TAA", "SAA·TAA", help_text="자산군 배분 흐름")
SHORTCUT_PORTFOLIO = NavShortcut(
    "📁 종목·Gap",
    "종합 포트",
    FOCUS_PORTFOLIO,
    "보유 vs 목표·positions 편집",
)
SHORTCUT_GAP = NavShortcut(
    "⚡ Gap·실행",
    "종합 포트",
    FOCUS_PORTFOLIO_GAP,
    "trade_actions",
)
SHORTCUT_OPS = NavShortcut(
    "🔒 운용승인",
    "종합 포트",
    FOCUS_PORTFOLIO_OPS,
    "AC·Execution Scope",
)
SHORTCUT_ALPHA_TARGET = NavShortcut(
    "🎯 알파 Target",
    "알파",
    FOCUS_ALPHA_TARGET,
    "target_draft 승인",
)
SHORTCUT_ALPHA_REVIEW = NavShortcut(
    "🔬 알파 보유리뷰",
    "알파",
    FOCUS_ALPHA_REVIEW,
    "TRIM/REPLACE",
)
SHORTCUT_EXPORT_DETAIL = NavShortcut(
    "📦 AI보내기 상세",
    "종합 포트",
    FOCUS_PORTFOLIO_EXPORT,
    "프롬프트·JSON 미리보기",
)
SHORTCUT_HEALTH = NavShortcut(
    "🩺 검증",
    "종합 포트",
    FOCUS_PORTFOLIO_HEALTH,
    "system_health",
)
SHORTCUT_DASHBOARD = NavShortcut("🏠 대시보드", "대시보드")
SHORTCUT_PMI = NavShortcut(
    "📊 PMI 확인",
    "PMI",
    help_text="S&P Global PMI KR 수동 확인 · data gate",
)
SHORTCUT_GUIDE = NavShortcut("📖 사용법", "사용법", help_text="빠른 시작·매일 흐름·FAQ")


def ai_export_prereq_shortcuts(*, include_alpha_target: bool = False) -> list[NavShortcut]:
    """AI 검증 ZIP 전 권장 확인 순서."""
    items = [
        SHORTCUT_SETTINGS_DATA,
        SHORTCUT_COMPASS,
        SHORTCUT_SAA,
        SHORTCUT_GAP,
        SHORTCUT_OPS,
    ]
    if include_alpha_target:
        items.append(SHORTCUT_ALPHA_TARGET)
    items.append(SHORTCUT_PORTFOLIO)
    return items


def draft_path_exists() -> bool:
    p = Path(__file__).resolve().parents[2] / "alpha_portfolio" / "data" / "output" / "target_draft.csv"
    return p.exists()


def render_sidebar_ai_checklist() -> None:
    st.markdown("**AI 검증 전 확인**")
    render_shortcut_row(
        ai_export_prereq_shortcuts(include_alpha_target=draft_path_exists()),
        key_prefix="sb_ai",
        columns=2,
    )
