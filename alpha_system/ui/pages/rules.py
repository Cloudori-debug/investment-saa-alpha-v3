"""규칙 탭 — config 조회(읽기 전용) + 가동 전 체크리스트."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.services.action_panels import open_panel, render_active_panel
from alpha_system.ui.services.approval_chrome import ap_copy
from alpha_system.ui.services.config_display import classify_config
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import consume_focus
from alpha_system.ui.services.ui_copy import copy_get

_CAT_LABEL = {
    "todo": "할 일",
    "locked": "잠금",
    "confirmed": "확정",
}


def render_rules(ctx: DashboardContext) -> None:
    consume_focus()

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

    with st.expander(ap_copy("live_yaml_title"), expanded=False):
        st.info(copy_get("rules", "edit_friction"))
        cfg_path = ctx.root / "alpha_system" / "config" / "alpha_system.yaml"
        rows, errs = classify_config(cfg_path)
        if errs:
            st.warning("스키마 검증: " + "; ".join(errs[:3]))
        todo_n = sum(1 for r in rows if r.category == "todo")
        st.caption(f"잠금/확정/할 일 — 할 일 {todo_n}건")
        filter_cat = st.selectbox(
            "분류 필터",
            ["전체", "todo", "locked", "confirmed"],
            format_func=lambda value: "전체" if value == "전체" else _CAT_LABEL[value],
            key="cfg_filter",
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
            label = ap_copy(
                {"todo": "yaml_todo", "locked": "yaml_locked", "confirmed": "yaml_confirmed"}[
                    row.category
                ]
            )
            st.markdown(
                f'<span class="{badge}">{label}</span> `{row.path}` = {val}',
                unsafe_allow_html=True,
            )
