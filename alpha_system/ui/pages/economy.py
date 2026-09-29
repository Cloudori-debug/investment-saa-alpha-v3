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
    _render_refresh(ctx.root, cached)
    _render_ladder(cached)
    _render_metrics(cached)
    _render_dividend_sleeve(ctx, cached)


def _render_refresh(root, signal) -> None:
    """Page-level FRED recalculate — under the hero, not under dividend."""
    if st.button(
        copy_get("economy", "refresh", default="다시 계산"),
        type="primary",
        use_container_width=True,
        key="economy_signal_refresh",
    ):
        try:
            refresh_economy_signal(root, api_key="")
        except Exception as exc:
            st.error(str(exc)[:240])
        else:
            st.rerun()
    when = format_fetched_at(signal.fetched_at) if signal is not None else ""
    if when:
        st.caption(
            copy_get(
                "economy",
                "refresh_as_of",
                default="마지막 계산 {when} · 금리·신용 단계만 (배당 표는 중기 정량)",
                when=when,
            )
        )
    else:
        st.caption(
            copy_get(
                "economy",
                "refresh_never",
                default="아직 계산 없음 · 누르면 금리·신용 단계를 갱신합니다 (배당 표 아님)",
            )
        )


def _render_dividend_sleeve(ctx: DashboardContext, signal) -> None:
    """Rate-regime hint only — dividend columns live on portfolio 후보 30."""
    from alpha_system.ui.services.economy_dividend_board import dividend_sleeve_hint

    stage = None if signal is None else signal.stage
    hint = dividend_sleeve_hint(stage)
    market = str(getattr(ctx, "screen_market", None) or "KOSPI")

    st.markdown(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_dividend", default="배당 · 환원"))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="eco-div eco-div-{_esc(hint.tone)}">'
        f'<div class="eco-div-title">{_esc(hint.title)}</div>'
        f'<div class="eco-div-body">{_esc(hint.detail)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "dividend_caption",
            default=(
                f"종목별 SR·배당%는 포트폴리오 › 후보 30 표에 표시합니다 "
                f"({market} 중기) · 경제 시그널은 금리 국면 힌트만 · "
                "순위·target 변경 없음 · 표 최신화는 확인 › ① 정량"
            ),
        )
    )


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
    st.caption(
        copy_get(
            "economy",
            "inputs_caption",
            default=(
                "가로바 = 지금 위치 · 눈금 = 여유↔주의↔긴축 경계 · "
                "아래 줄 = 그 구간으로 읽히는 이유"
            ),
        )
    )
    if signal is None or not signal.inputs:
        st.caption(
            copy_get("economy", "need_fred", default="설정 › API 키에 FRED 키가 있으면 계산합니다.")
        )
        return
    cards = []
    for row in metric_rows(signal):
        reading = str(row.get("reading") or "").strip()
        reading_html = (
            f'<div class="eco-m-read">{_esc(reading)}</div>' if reading else ""
        )
        cards.append(
            '<div class="eco-metric">'
            f'<div class="eco-m-title">{_esc(row["title"])}</div>'
            f'<span class="eco-stress eco-{_esc(row["tone"])}">{_esc(row["stress"])}</span>'
            f'<div class="eco-val">{_esc(row["value"])}</div>'
            f'<div class="eco-m-hint">{_esc(row["hint"])}</div>'
            f'<div class="eco-date">{_esc(row["as_of"])}</div>'
            f"{_slider_html(row.get('slider'))}"
            f"{reading_html}"
            "</div>"
        )
    st.markdown(f'<div class="eco-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _slider_html(slider: object) -> str:
    if not isinstance(slider, dict):
        return ""
    segs = []
    for seg in slider.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        width = seg.get("width")
        tone = seg.get("tone") or "off"
        segs.append(
            f'<span class="eco-slide-seg eco-{_esc(tone)}" style="width:{float(width):g}%"></span>'
        )
    ticks = []
    for tick in slider.get("ticks") or []:
        if not isinstance(tick, dict):
            continue
        ticks.append(
            f'<span class="eco-slide-tick" style="left:{float(tick["pct"]):g}%">'
            f'<span class="eco-slide-tick-mark"></span>'
            f'<span class="eco-slide-tick-lab">{_esc(tick["label"])}</span>'
            "</span>"
        )
    mark_tone = _esc(slider.get("tone") or "off")
    pct = float(slider.get("pct") or 0)
    clamp = " is-clamp" if slider.get("clamped") else ""
    return (
        f'<div class="eco-slide{clamp}">'
        f'<div class="eco-slide-track">{"".join(segs)}'
        f'<span class="eco-slide-mark eco-{mark_tone}" style="left:{pct:g}%"></span>'
        "</div>"
        f'<div class="eco-slide-ticks">{"".join(ticks)}</div>'
        "</div>"
    )
