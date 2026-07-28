"""규칙 탭 — config 조회(읽기 전용) + 가동 전 체크리스트."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.services.action_panels import open_panel, render_active_panel
from alpha_system.ui.services.config_display import classify_config
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import FOCUS_RULES_PREFIX, consume_focus
from alpha_system.ui.services.ui_copy import copy_get, format_tranche_label, tranche_display


def render_rules(ctx: DashboardContext) -> None:
    focus = consume_focus()
    target_tid = None
    if focus and focus.startswith(FOCUS_RULES_PREFIX):
        target_tid = focus[len(FOCUS_RULES_PREFIX) :]

    st.subheader("가동 전 체크리스트")
    if ctx.checklist is not None:
        st.caption(f"{ctx.checklist.done}/{ctx.checklist.total} 충족")
        for item in ctx.checklist.items:
            cols = st.columns([5, 1])
            if item.ok:
                with cols[0]:
                    st.markdown(
                        f'<div class="alpha-action-item muted">✅ <strong>{item.title}</strong> '
                        "— 완료 · 조회만</div>",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button("조회", key=f"rules_check_view_{item.key}"):
                        st.session_state["rules_check_view"] = item.key
            else:
                with cols[0]:
                    st.markdown(
                        f'<div class="alpha-action-item">○ <strong>{item.title}</strong><br/>'
                        f"{item.why}</div>",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button("처리", key=f"rules_check_open_{item.key}"):
                        open_panel(f"check_{item.key}")
        viewed = st.session_state.get("rules_check_view")
        viewed_item = next((item for item in ctx.checklist.items if item.key == viewed), None)
        if viewed_item:
            st.caption(
                f"✅ {viewed_item.title} — {viewed_item.why} · 해결 경로: {viewed_item.todo}"
            )
        render_active_panel(ctx)
    else:
        st.caption("체크리스트 없음")

    st.divider()
    st.subheader("트랜치 규칙")
    for tid in ("T1", "T2", "T3", "T4"):
        tcfg = ctx.cfg.tranches[tid]
        name, short = tranche_display(tid)
        # Prefer config display fields when set
        if getattr(tcfg, "display_name", None):
            name = tcfg.display_name or name
        if getattr(tcfg, "short_desc", None):
            short = tcfg.short_desc or short
        expanded = target_tid == tid
        with st.expander(f"{format_tranche_label(tid)}", expanded=expanded):
            st.markdown(short or tcfg.description)
            st.markdown(f"- weight: `{tcfg.weight}`")
            st.markdown(f"- trigger_type: `{tcfg.trigger_type.value}`")
            if tcfg.event_ids:
                st.markdown(f"- event_ids: `{', '.join(tcfg.event_ids)}`")
            if tcfg.valuation_band:
                st.markdown(f"- valuation_band: `{tcfg.valuation_band}`")
            if tcfg.hybrid_rules:
                st.markdown(f"- hybrid_rules: `{tcfg.hybrid_rules}`")
            st.caption(tcfg.description)

    st.divider()
    st.subheader("Config 조회 (읽기 전용)")
    st.info(copy_get("rules", "edit_friction"))
    cfg_path = ctx.root / "alpha_system" / "config" / "alpha_system.yaml"
    rows, errs = classify_config(cfg_path)
    if errs:
        st.warning("스키마 검증: " + "; ".join(errs[:3]))
    todo_n = sum(1 for r in rows if r.category == "todo")
    st.caption(f"잠금/확정/TODO — TODO {todo_n}건")
    filter_cat = st.selectbox(
        "분류 필터", ["전체", "todo", "locked", "confirmed"], key="cfg_filter"
    )
    for row in rows:
        if filter_cat != "전체" and row.category != filter_cat:
            continue
        badge = {
            "todo": "alpha-badge-warn",
            "locked": "alpha-badge-ok",
            "confirmed": "alpha-badge-ok",
        }[row.category]
        val = row.value
        if isinstance(val, (list, dict)):
            val = str(val)[:120] + ("…" if len(str(val)) > 120 else "")
        st.markdown(
            f'<span class="{badge}">{row.category.upper()}</span> `{row.path}` = {val}',
            unsafe_allow_html=True,
        )
