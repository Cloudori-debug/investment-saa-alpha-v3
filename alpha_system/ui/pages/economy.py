"""Economy signal — Review-only 5-stage equity/cash ladder."""

from __future__ import annotations

import html

import streamlit as st

from alpha_system.economy_signal import load_cached_signal, refresh_economy_signal
from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.economy_display import (
    format_fetched_at,
    hero_copy,
    ladder_rows,
    metric_rows,
)
from alpha_system.ui.services.ui_copy import copy_get


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def render_economy(ctx: DashboardContext) -> None:
    page_head(
        kicker=copy_get("economy", "page_kicker", default="경제 시그널"),
        title=copy_get("economy", "page_title", default="개별주 · 단기채"),
        lead=copy_get(
            "economy",
            "page_lead",
            default="금리와 신용으로 주식 비중만 제안합니다. 종목 순위와 target 파일은 그대로입니다.",
        ),
    )
    cached = load_cached_signal(ctx.root)
    _render_hero(cached)
    _render_ladder(cached)
    _render_metrics(cached)
    if st.button(copy_get("economy", "refresh", default="다시 계산"), key="economy_signal_refresh"):
        try:
            refresh_economy_signal(ctx.root, api_key="")
        except Exception as exc:
            st.error(str(exc)[:240])
        else:
            st.rerun()


def _render_hero(signal) -> None:
    if signal is None:
        st.markdown(
            '<div class="eco-hero"><div class="eco-card">'
            f'<div class="eco-kicker">{_esc(copy_get("economy", "empty_kicker", default="아직 없음"))}</div>'
            f'<div class="eco-title">{_esc(copy_get("economy", "empty", default="다시 계산을 누르면 단계가 나옵니다."))}</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )
        return
    hero = hero_copy(signal)
    when = format_fetched_at(signal.fetched_at)
    meta = []
    if hero.get("scoreline"):
        meta.append(_esc(hero["scoreline"]))
    if when:
        meta.append(f"계산 {_esc(when)}")
    meta_html = f'<p class="eco-when">{" · ".join(meta)}</p>' if meta else ""
    st.markdown(
        f"""
<div class="eco-hero">
  <div class="eco-card eco-now">
    <div class="eco-kicker">{_esc(hero["kicker"])}</div>
    <div class="eco-title">{_esc(hero["title"])}</div>
    <div class="eco-split">
      <div>
        <span class="eco-pct">{_esc(hero["equity"])}</span>
        <span class="eco-pct-label">개별주</span>
      </div>
      <div>
        <span class="eco-pct">{_esc(hero["cash"])}</span>
        <span class="eco-pct-label">단기채</span>
      </div>
    </div>
    <p class="eco-why">{_esc(hero["why"])}</p>
    {meta_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_ladder(signal) -> None:
    current = None if signal is None else signal.stage
    cells = []
    for row in ladder_rows(current):
        now_cls = " is-now" if row["current"] else ""
        mark = '<div class="eco-step-now">지금</div>' if row["current"] else ""
        cells.append(
            f'<div class="eco-step{now_cls}">'
            f'<div class="eco-step-n">{int(row["stage"])}단계</div>'
            f'<div class="eco-step-label">{_esc(row["label"])}</div>'
            f'<div class="eco-step-split">{_esc(row["equity"])} / {_esc(row["cash"])}</div>'
            f"{mark}"
            "</div>"
        )
    st.markdown(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_ladder", default="단계"))}</div>'
        f'<div class="eco-steps">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def _render_metrics(signal) -> None:
    st.markdown(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_inputs", default="근거"))}</div>',
        unsafe_allow_html=True,
    )
    if signal is None or not signal.inputs:
        st.caption(
            copy_get("economy", "need_fred", default="설정 › API 키에 FRED 키가 있으면 계산합니다.")
        )
        return
    cards = []
    for row in metric_rows(signal):
        cards.append(
            '<div class="eco-metric">'
            f'<div class="eco-m-title">{_esc(row["title"])}</div>'
            f'<span class="eco-stress eco-{_esc(row["tone"])}">{_esc(row["stress"])}</span>'
            f'<div class="eco-val">{_esc(row["value"])}</div>'
            f'<div class="eco-m-hint">{_esc(row["hint"])}</div>'
            f'<div class="eco-date">{_esc(row["as_of"])}</div>'
            "</div>"
        )
    st.markdown(f'<div class="eco-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
