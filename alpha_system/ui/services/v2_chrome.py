"""v2 shell chrome — sidebar main menu + slim header (ops assistant IA)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import streamlit as st
import yaml

from alpha_system.scoring.pending_rescore import load_pending, pending_path
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import (
    FOCUS_REGIME,
    FOCUS_WEEKLY_QUAL,
    NAV_MAIN_PAGES,
    NAV_MORE_PAGES,
    PAGE_APPROVAL,
    PAGE_HINTS,
    PAGE_REGIME,
    navigate,
    page_display_name,
)
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


def render_primary_nav(
    pages: Sequence[str],
    *,
    key: str = "alpha_page",
    approval_badge: int | None = None,
) -> str:
    """Sidebar: 오늘 / 확인 / 포트폴리오 + 더보기."""
    options = list(pages)
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    current = str(st.session_state[key])

    st.markdown(
        '<div class="v2-side-nav-brand">'
        '<div class="v2-side-nav-title">SAA 알파</div>'
        '<div class="v2-side-nav-sub">운용 비서 · 자동매매 아님</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="v2-side-nav-label">오늘 메뉴</div>',
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
        st.caption("저널 · 시장 참고 · API/백업")
        for page in more_pages:
            _nav_button(page)

    return str(st.session_state.get(key) or options[0])


def render_app_header(*, as_of: str | None = None, page: str | None = None) -> None:
    """Slim content header — brand in sidebar; friendly display name in content."""
    title = page_display_name(page) if page else ""
    page_bit = f"<strong>{title}</strong>" if title else ""
    as_of_html = f'<span class="v2-asof">as_of {as_of}</span>' if as_of else ""
    st.markdown(
        f"""
<div class="v2-shell-header v2-shell-header-slim">
  <div class="v2-shell-page">{page_bit}</div>
  {as_of_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_ops_strip(ctx: DashboardContext) -> None:
    """Deprecated on home shell — kept for optional deep pages / tests."""
    waiting_n = _count_waiting_targets(ctx)
    rescore_n = len(load_pending(pending_path(ctx.root)))
    regime_info = _regime_info(ctx.root)

    cards = [
        {
            "title": "분할매수 (SCALE_IN)",
            "body": "신규 매수는 3회×균등 · 회차 사이 ≥3거래일 · 하루 전액 투입 금지",
            "tone": "ok",
        },
        {
            "title": "목표가 대기",
            "body": (
                f"제안 {waiting_n}종에 exit 목표가 없음 → 확인에서 채운 뒤 편입"
                if waiting_n
                else "제안 북 전 종목 목표가 있음 · 편입 게이트 통과 가능"
            ),
            "tone": "warn" if waiting_n else "ok",
        },
        {
            "title": "재채점 검토",
            "body": (
                f"대기 {rescore_n}건 · 점수 자동변경 없음 · 사람이 검토만"
                if rescore_n
                else "실적·등급 하향 등 재채점 신호 없음"
            ),
            "tone": "warn" if rescore_n else "ok",
        },
        {
            "title": f"시장 레짐 · {regime_info['label']}",
            "body": regime_info["detail"],
            "tone": regime_info["tone"],
        },
    ]

    parts = []
    for card in cards:
        parts.append(
            f'<div class="v2-ops-card v2-ops-card-{card["tone"]}">'
            f'<span class="v2-ops-card-title">{card["title"]}</span>'
            f'<span class="v2-ops-card-body">{card["body"]}</span>'
            f"</div>"
        )
    st.markdown(
        f'<div class="v2-ops-strip">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if waiting_n and st.button(
            f"목표가 대기 {waiting_n}종 → 확인",
            key="v2_chip_targets",
            use_container_width=True,
        ):
            navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)
    with c2:
        if rescore_n and st.button(
            f"재채점 {rescore_n}건 → 확인",
            key="v2_chip_rescore",
            use_container_width=True,
        ):
            navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)
    with c3:
        if st.button(
            f"레짐 · {regime_info.get('label') or '—'} →",
            key="v2_chip_regime",
            use_container_width=True,
        ):
            navigate(PAGE_REGIME, focus=FOCUS_REGIME)


def render_regime_concerns(*, expanded: bool = False) -> None:
    """Pure-auto caveats — used on 레짐 page (not global ops strip)."""
    title = copy_get("regime", "concerns_title", default="레짐 순수 자동 — 유의")
    raw = (load_ui_copy().get("regime") or {}).get("concerns") or []
    items = [str(x) for x in raw if str(x).strip()]
    if not items:
        return
    with st.expander(title, expanded=expanded):
        for line in items:
            st.markdown(f"- {line}")


def _render_regime_concerns() -> None:
    render_regime_concerns(expanded=False)


def _count_waiting_targets(ctx: DashboardContext) -> int:
    """Proposal rows without usable exit YAML valuation."""
    path = ctx.root / "data" / "kr_alpha_exit_targets.yaml"
    tickers_map: dict[str, Any] = {}
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            tickers_map = raw.get("tickers") or {}
        except (OSError, yaml.YAMLError):
            tickers_map = {}

    def has_target(tk: str) -> bool:
        entry = None
        for k, v in tickers_map.items():
            if str(k).zfill(6) == str(tk).zfill(6):
                entry = v
                break
        if not isinstance(entry, dict):
            return False
        if entry.get("target_price") is not None:
            return True
        val = entry.get("valuation")
        return isinstance(val, dict) and val.get("pbr_max") is not None

    rows = getattr(ctx, "portfolio_rows", None) or []
    if not rows:
        return 0
    return sum(1 for r in rows if not has_target(r.ticker))


def _regime_sync_mode(root: Path) -> str:
    path = root / "data" / "tier2_sources.yaml"
    if not path.exists():
        return "respect_override"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mode = str(raw.get("regime_sync_mode") or "respect_override").strip().lower()
        if mode in {"pure_auto", "auto", "pure"}:
            return "pure_auto"
    except (OSError, yaml.YAMLError):
        pass
    return "respect_override"


def regime_info(root: Path) -> dict[str, Any]:
    """Read compass Tier-1 market_indicators; pure_auto shows computed sync semantics."""
    pure = _regime_sync_mode(root) == "pure_auto"
    path = root / "data" / "market_indicators.csv"
    empty: dict[str, Any] = {
        "label": "—",
        "detail": "market_indicators.csv 없음 · 나침반 Tier1 미로드",
        "tone": "muted",
        "pure_auto": pure,
    }
    if not path.exists():
        return empty
    try:
        import pandas as pd

        df = pd.read_csv(path)
        if df.empty or "regime" not in df.columns:
            return empty
        row = df.iloc[-1]
        label = str(row.get("regime") or "—").strip() or "—"
        expires = str(row.get("regime_expires_date") or "").strip()
        reason = str(row.get("regime_override_reason") or "").strip()
        set_d = str(row.get("regime_set_date") or "").strip()
        bits: list[str] = []
        if pure:
            mode_lbl = copy_get("regime", "mode_pure_auto", default="순수 자동")
            bits.append(mode_lbl)
            bits.append(
                copy_get(
                    "regime",
                    "card_detail_pure",
                    default="산출=적용 · 일 파이프라인 갱신 · QVM 순위 불변",
                )
            )
        else:
            bits.append(
                copy_get(
                    "regime",
                    "card_detail_override",
                    default="나침반 지표 파일 · 사람 재분류 가능(자동 완화 금지)",
                )
            )
        if expires:
            bits.append(f"만료 {expires}")
        if set_d:
            bits.append(f"설정 {set_d}")
        if reason and reason not in {"auto_computed_regime", "auto_computed_regime_pure"}:
            short = reason if len(reason) <= 72 else reason[:69] + "…"
            bits.append(short)
        elif reason.startswith("auto_computed"):
            bits.append(reason)
        tone = (
            "warn"
            if "CAUTION" in label.upper()
            or "CRISIS" in label.upper()
            or "RISK_OFF" in label.upper()
            else "muted"
        )
        if pure and tone == "muted":
            tone = "ok"
        if label in {"—", "nan", "None"}:
            tone = "muted"
        return {"label": label, "detail": " · ".join(bits), "tone": tone, "pure_auto": pure}
    except Exception:
        return empty


# Back-compat for any private callers
_regime_info = regime_info
