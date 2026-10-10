"""Economy compass — global sleeves + rate regime (Review-only)."""

from __future__ import annotations

import html

import streamlit as st

from alpha_system.economy_compass import build_compass, save_compass_snapshot
from alpha_system.economy_signal import load_cached_signal, refresh_economy_signal
from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.economy_compass_board import (
    history_panel_html,
    metric_sleeve_lines_html,
    sleeves_panel_html,
)
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
        kicker=copy_get("economy", "page_kicker", default="경제 나침반"),
        title=copy_get(
            "economy", "page_title", default="글로벌 슬리브 · 금리 국면"
        ),
        lead=copy_get(
            "economy",
            "page_lead",
            default=(
                "숲=주식·국채·현금·금 Review · 나무=포트폴리오 QVM. "
                "순위·target 자동 변경 없음."
            ),
        ),
    )
    cached = load_cached_signal(ctx.root)
    compass = build_compass(cached)
    _render_hero(cached)
    _render_refresh(ctx.root, cached)
    _render_ladder(cached)
    _render_sleeves(compass)
    _render_metrics(cached, compass)
    _render_history(compass)
    _render_playbook(cached)
    _render_forest_checklist(cached)
    _render_kr_link(compass)
    _render_holdings_gap(ctx)
    _render_dividend_sleeve(ctx, cached)


def _render_sleeves(compass) -> None:
    st.markdown(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_sleeves", default="글로벌 슬리브"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "sleeves_caption",
            default=(
                "권고 밴드 · Review-only · ETF·현금·채권은 사람이 맞춤 · "
                "한국 종목 순위 불변"
            ),
        )
    )
    st.markdown(sleeves_panel_html(compass), unsafe_allow_html=True)


def _render_history(compass) -> None:
    st.markdown(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_history", default="과거 유사국면"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "history_caption",
            default=(
                "같은 긴축 버킷의 사전계산 월수익률 빈도 · "
                "온라인 전수 백테스트 아님 · 참고용"
            ),
        )
    )
    st.markdown(history_panel_html(compass), unsafe_allow_html=True)


def _render_kr_link(compass) -> None:
    st.markdown(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_kr_link", default="한국 주식"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="eco-compass-block">'
        f'<div class="eco-kr-link">{_esc(compass.kr_link)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "kr_link_caption",
            default=(
                "포트폴리오 ③ 최종 제안·노른자 대기 · "
                "나침반이 편입·target을 바꾸지 않음"
            ),
        )
    )


def _render_refresh(root, signal) -> None:
    """Page-level FRED recalculate — under the hero, not under dividend."""
    if st.button(
        copy_get("economy", "refresh", default="다시 계산"),
        type="primary",
        use_container_width=True,
        key="economy_signal_refresh",
    ):
        try:
            signal = refresh_economy_signal(root, api_key="")
            save_compass_snapshot(root, build_compass(signal))
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


def _todo_split_bar_html(
    equity_pct: float | None,
    cash_pct: float | None,
    *,
    eq_label: str = "개별주",
    cash_label: str = "단기채",
) -> str:
    if equity_pct is None or cash_pct is None:
        return ""
    eq = max(0.0, min(100.0, float(equity_pct)))
    cash = max(0.0, min(100.0, float(cash_pct)))
    total = eq + cash
    if total <= 0:
        return ""
    eq_w = 100.0 * eq / total
    cash_w = 100.0 * cash / total
    return (
        f'<div class="eco-todo-bar" role="img" '
        f'aria-label="{_esc(eq_label)} {eq:g}% · {_esc(cash_label)} {cash:g}%">'
        f'<span class="eco-todo-bar-eq" style="width:{eq_w:g}%">'
        f'<span class="eco-todo-bar-lab">{_esc(eq_label)} {int(round(eq))}%</span></span>'
        f'<span class="eco-todo-bar-cash" style="width:{cash_w:g}%">'
        f'<span class="eco-todo-bar-lab">{_esc(cash_label)} {int(round(cash))}%</span></span>'
        f"</div>"
    )


def _todo_cards_html(cards) -> str:
    tiles = []
    for i, card in enumerate(cards, start=1):
        tiles.append(
            f'<div class="eco-todo-card">'
            f'<div class="eco-todo-n">{i:02d}</div>'
            f'<div class="eco-todo-label">{_esc(card.label)}</div>'
            f'<div class="eco-todo-body">{_esc(card.body)}</div>'
            f"</div>"
        )
    return f'<div class="eco-todo-grid">{"".join(tiles)}</div>'


def _render_playbook(signal) -> None:
    from alpha_system.ui.services.economy_playbook import stage_playbook

    stage = None if signal is None else signal.stage
    book = stage_playbook(stage)
    st.markdown(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_playbook", default="지금 할 일"))}</div>',
        unsafe_allow_html=True,
    )
    bar = _todo_split_bar_html(book.equity_pct, book.cash_pct)
    st.markdown(
        f'<div class="eco-todo eco-todo-{_esc(book.tone)}">'
        f'<div class="eco-todo-head">'
        f'<div class="eco-todo-title">{_esc(book.title)}</div>'
        f'<div class="eco-todo-sub">{_esc(book.equity_cash)}</div>'
        f"{bar}"
        f"</div>"
        f"{_todo_cards_html(book.cards)}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "playbook_caption",
            default="Review-only · 순위·target 자동 변경 없음 · 단기채는 사람이 맞춤",
        )
    )


def _render_forest_checklist(signal) -> None:
    """Whole-net-worth defense reminders — below alpha equity/cash playbook."""
    from alpha_system.ui.services.economy_forest_checklist import stage_forest_checklist

    stage = None if signal is None else signal.stage
    book = stage_forest_checklist(stage)
    st.markdown(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_forest", default="숲 방어 체크"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="eco-todo eco-todo-forest eco-todo-{_esc(book.tone)}">'
        f'<div class="eco-todo-head">'
        f'<div class="eco-todo-title">{_esc(book.title)}</div>'
        f'<div class="eco-todo-sub">{_esc(book.focus)}</div>'
        f"</div>"
        f"{_todo_cards_html(book.cards)}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "forest_caption",
            default=(
                "재산 전체(현금·채권·금·해외) 알림 · 위 「지금 할 일」은 한국 주식·단기채 · "
                "순위·target 자동 변경 없음"
            ),
        )
    )


def _render_holdings_gap(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.economy_playbook import holdings_proposal_gap
    from alpha_system.ui.services.screen_horizon import is_short

    gap = holdings_proposal_gap(
        getattr(ctx, "ops_portfolio_rows", None),
        getattr(ctx, "portfolio_rows", None),
    )
    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    book_lab = "단기" if is_short(getattr(ctx, "screen_horizon", None)) else "중기"
    st.markdown(
        f'<div class="eco-sec">{_esc(copy_get("economy", "sec_gap", default="보유 · 제안 괴리"))}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "gap_caption",
            default=(
                f"{market} · {book_lab} · 실보유 vs 최종 제안 · "
                "교체·편입은 사람 Review · target 자동기입 없음"
            ),
        )
    )
    if gap.no_books:
        st.info(
            copy_get(
                "economy",
                "gap_empty",
                default=(
                    "실보유 또는 최종 제안이 비어 있습니다. "
                    "포트폴리오에서 보유 체크·제안 확정 후 다시 보세요."
                ),
            )
        )
        return

    def _chips(rows: list, empty_label: str) -> str:
        if not rows:
            return f'<span class="eco-gap-empty">{_esc(empty_label)}</span>'
        return "".join(
            f'<span class="eco-gap-chip">{_esc(r.name)} '
            f'<span class="eco-gap-tk">{_esc(r.ticker)}</span></span>'
            for r in rows
        )

    st.markdown(
        '<div class="eco-gap-grid">'
        f'<div class="eco-gap-card eco-gap-out">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_held_out", default="보유 · 제안 밖"))}'
        f' · {len(gap.held_not_proposed)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_held_out_hint", default="교체·축소 Review"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.held_not_proposed, "없음")}</div>'
        f"</div>"
        f'<div class="eco-gap-card eco-gap-in">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_prop_in", default="제안 · 미보유"))}'
        f' · {len(gap.proposed_not_held)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_prop_in_hint", default="편입 Review"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.proposed_not_held, "없음")}</div>'
        f"</div>"
        f'<div class="eco-gap-card eco-gap-ok">'
        f'<div class="eco-gap-h">{_esc(copy_get("economy", "gap_overlap", default="보유 · 제안 일치"))}'
        f' · {len(gap.overlap)}</div>'
        f'<div class="eco-gap-hint">{_esc(copy_get("economy", "gap_overlap_hint", default="유지 후보"))}</div>'
        f'<div class="eco-gap-chips">{_chips(gap.overlap, "없음")}</div>'
        f"</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if not gap.has_gaps:
        st.caption(
            copy_get(
                "economy",
                "gap_aligned",
                default="보유와 최종 제안이 같습니다. 비중(단기채)만 단계에 맞추면 됩니다.",
            )
        )


def _render_metrics(signal, compass=None) -> None:
    st.markdown(
        f'<div class="eco-sec">'
        f'{_esc(copy_get("economy", "sec_inputs", default="근거 · 읽는 법"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "economy",
            "inputs_caption",
            default="가로바=위치 · 아래=구간 해석 · 슬리브 함의",
        )
    )
    if signal is None or not signal.inputs:
        st.caption(
            copy_get("economy", "need_fred", default="설정 › API 키에 FRED 키가 있으면 계산합니다.")
        )
        return
    hint_by_key = {}
    if compass is not None:
        hint_by_key = {h.key: h for h in compass.metric_hints}
    cards = []
    for row in metric_rows(signal):
        reading = str(row.get("reading") or "").strip()
        reading_html = (
            f'<div class="eco-m-read">{_esc(reading)}</div>' if reading else ""
        )
        hint = hint_by_key.get(str(row.get("key") or ""))
        sleeve_html = (
            f'<div class="eco-m-sleeve-v">{_esc(hint.sleeve_implication)}</div>'
            if hint and hint.sleeve_implication
            else ""
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
            f"{sleeve_html}"
            "</div>"
        )
    st.markdown(f'<div class="eco-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    if compass is not None and not any("eco-m-sleeve-v" in c for c in cards):
        extra = metric_sleeve_lines_html(compass)
        if extra:
            st.markdown(extra, unsafe_allow_html=True)


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
