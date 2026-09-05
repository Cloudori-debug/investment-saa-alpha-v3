"""Shared chrome for 확인 (approval) tabs — one visual language."""

from __future__ import annotations

import html
from typing import Sequence

import streamlit as st

from alpha_system.ui.services.ui_copy import copy_get


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def page_head(*, kicker: str = "", title: str = "", lead: str = "") -> None:
    """Top identity strip — same on every menu."""
    bits = ['<div class="ap-page-head">']
    if kicker:
        bits.append(f'<div class="ap-page-kicker">{_esc(kicker)}</div>')
    if title:
        bits.append(f'<div class="ap-page-title">{_esc(title)}</div>')
    if lead:
        bits.append(f'<p class="ap-page-lead">{_esc(lead)}</p>')
    bits.append("</div>")
    st.markdown("\n".join(bits), unsafe_allow_html=True)


def page_tabs(label: str, options: Sequence[str], *, key: str) -> str:
    """Segmented control with the shared tab-label chrome."""
    items = [str(x) for x in options if str(x)]
    if not items:
        raise ValueError("page_tabs needs at least one option")
    st.markdown(f'<div class="ap-tab-label">{_esc(label)}</div>', unsafe_allow_html=True)
    section = st.segmented_control(
        label,
        items,
        selection_mode="single",
        required=True,
        label_visibility="collapsed",
        key=key,
        width="stretch",
    )
    return str(section) if section is not None else items[0]


def ap_head(*, kicker: str, title: str, desc: str) -> None:
    st.markdown(
        f"""
<div class="ap-panel">
  <div class="ap-panel-kicker">{_esc(kicker)}</div>
  <div class="ap-panel-title">{_esc(title)}</div>
  <p class="ap-panel-desc">{_esc(desc)}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def ap_subhead(title: str, *, desc: str = "") -> None:
    extra = f'<p class="ap-panel-desc">{_esc(desc)}</p>' if desc else ""
    st.markdown(
        f'<div class="ap-subblock-title">{_esc(title)}</div>{extra}',
        unsafe_allow_html=True,
    )


def ap_chips(items: Sequence[tuple[str, str]]) -> None:
    """items: (label, tone) where tone is ok | wait | off."""
    if not items:
        return
    bits = []
    for label, tone in items:
        cls = {"ok": "ap-chip-ok", "wait": "ap-chip-wait", "off": "ap-chip-off"}.get(
            tone, "ap-chip-off"
        )
        bits.append(f'<span class="ap-chip {cls}">{_esc(label)}</span>')
    st.markdown(
        f'<div class="ap-chip-row">{"".join(bits)}</div>',
        unsafe_allow_html=True,
    )


def ap_copy(*keys: str, default: str = "", **fmt: object) -> str:
    return copy_get("approval", *keys, default=default, **fmt)


def ap_step_label() -> None:
    st.markdown(
        f'<div class="ap-tab-label">{_esc(ap_copy("step_label", default="진행"))}</div>',
        unsafe_allow_html=True,
    )


def ap_freshness_table(sources) -> None:
    if not sources:
        return
    rows = []
    for src in sources:
        if not getattr(src, "exists", True):
            tone = ap_copy("source_missing", default="없음")
            tone_cls = "ap-fresh-missing"
        elif getattr(src, "stale", False):
            tone = ap_copy("source_stale", default="오래됨")
            tone_cls = "ap-fresh-stale"
        else:
            tone = ap_copy("source_ok", default="최신")
            tone_cls = "ap-fresh-ok"
        rec = (
            f"권장 {src.recommended_days}일"
            if getattr(src, "recommended_days", None)
            else "수동"
        )
        as_of = src.as_of.isoformat() if getattr(src, "as_of", None) else "—"
        rows.append(
            "<tr>"
            f"<td>{_esc(src.label)}<div class='ap-fresh-path'>{_esc(src.path)}</div></td>"
            f"<td><span class='ap-chip {tone_cls}'>{_esc(tone)}</span></td>"
            f"<td>{_esc(as_of)}</td>"
            f"<td>{_esc(rec)}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='ap-fresh-table'><thead><tr>"
        "<th>자료</th><th>상태</th><th>기준일</th><th>주기</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )
