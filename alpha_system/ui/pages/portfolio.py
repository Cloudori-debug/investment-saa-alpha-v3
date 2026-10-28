"""Portfolio page — observation 30, proposal book, ops holdings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as _date
from pathlib import Path

import html
import pandas as pd
import streamlit as st

from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.sizing.qual_overlay import (
    apply_evidence_withdrawn_gates,
    apply_opendart_flag_gates,
    journal_overlay_change,
    load_qual_overlay,
    overlay_path,
    save_qual_overlay,
)
from alpha_system.sizing.target_gate import collect_above_justified_target_tickers_from_root
from alpha_system.ui.services.context import DashboardContext, PortfolioRow
from alpha_system.ui.services.cecs_workbench import (
    build_relative_cutoff_ladder,
    confirm_score_cutoff,
    recommended_absolute_cutoff_option,
)
from alpha_system.ui.services.candidate_ai_export import build_candidate_ai_export
from alpha_system.ui.services.nav import consume_focus
from alpha_system.ui.services.portfolio_widgets import render_portfolio_bullets
from alpha_system.ui.services.rank_watchboard import (
    build_rank_watchboard,
    build_watch_table_rows,
    load_sector_labels,
    load_watch_metrics,
    naver_fchart_url,
    naver_name_chart_html,
    watch_tone_label,
)
from alpha_system.ui.services.sector_regime_fit import (
    build_sector_regime_board,
    fit_label_for_ticker,
    fit_why_for_ticker,
)

# 레짐 보완 후보 박스는 기회비용(주의·슬롯)만 키워 제거.
# 국면적합 열은 후보30 안에서만 Review 힌트로 유지.
from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.screen_market import render_screen_market_nav
from alpha_system.screen_book import (
    is_kosdaq,
    save_kosdaq_policy,
    target_names_band,
    watch_max,
)
from alpha_system.ui.theme_prefs import watch_row_styles

try:
    from alpha_system.screen_book import is_short, save_short_policy
except ImportError:  # pragma: no cover — older screen_book without short horizon

    def is_short(horizon: object) -> bool:
        return str(horizon or "").strip().lower() in {"short", "단기", "st"}

    def save_short_policy(*_a, **_k):  # type: ignore[misc]
        return None


def _book_keys(ctx: DashboardContext) -> str:
    mkt = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    hz = str(getattr(ctx, "screen_horizon", "mid") or "mid")
    return f"{mkt}_{hz}"


def _source_dir(ctx: DashboardContext):
    return getattr(ctx, "source_data_dir", None) or ctx.data_dir


def _watch_session_keys(ctx: DashboardContext) -> tuple[str, str, str]:
    tag = _book_keys(ctx)
    return f"pf_watch_{tag}", f"pf_watch_{tag}_sig", f"pf_watch_{tag}_last"


def _reset_watch_picker(ctx: DashboardContext, tickers: list[str]) -> None:
    key, _sig, last = _watch_session_keys(ctx)
    st.session_state.pop(key, None)
    st.session_state[last] = tuple(sorted(tickers))


def _watch_hold_flags(edited: object, *, n: int) -> list[bool]:
    """Read「보유」flags from data_editor frame (or arrow-fallback event)."""
    if n <= 0:
        return []
    # Native data_editor → DataFrame with 보유 column.
    try:
        import pandas as pd

        if isinstance(edited, pd.DataFrame) and "보유" in edited.columns:
            flags = [bool(v) for v in edited["보유"].tolist()[:n]]
            if len(flags) < n:
                flags.extend([False] * (n - len(flags)))
            return flags
    except Exception:  # noqa: BLE001 — fall through to selection event
        pass
    # HTML fallback may return DataframeFallbackEvent(selection.rows).
    rows = list(getattr(getattr(edited, "selection", None), "rows", None) or [])
    on = {int(i) for i in rows if 0 <= int(i) < n}
    return [i in on for i in range(n)]



def _pair_mid_short_ctx(
    ctx: DashboardContext,
) -> tuple[DashboardContext, DashboardContext]:
    """한 페이지에 중기+단기를 같이 쓰기 위해 짝 컨텍스트 로드."""
    from alpha_system.ui.services.context import load_context

    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    root = Path(ctx.root)
    if is_short(getattr(ctx, "screen_horizon", None)):
        short_ctx = ctx
        mid_ctx = load_context(root, market=market, horizon="mid")
    else:
        mid_ctx = ctx
        try:
            short_ctx = load_context(root, market=market, horizon="short")
        except Exception:  # noqa: BLE001
            short_ctx = ctx
    return mid_ctx, short_ctx


def render_portfolio(
    ctx: DashboardContext,
    *,
    proposal_eligible_sorter: Callable[
        [list[PortfolioRow], DashboardContext], list[PortfolioRow]
    ]
    | None = None,
    proposal_final_sort_label: str | None = None,
) -> None:
    consume_focus()  # confirmation CTAs land here; no sub-tabs
    if "holdings_input_open" not in st.session_state:
        st.session_state["holdings_input_open"] = True

    page_head(
        kicker=copy_get("portfolio", "page_kicker", default="포트폴리오"),
        title=copy_get(
            "portfolio", "page_title", default="알파 위성 · 오늘 매매"
        ),
        lead=copy_get(
            "portfolio",
            "page_lead",
            default=(
                "①오늘 순서(팔→유지→사) → ②목표 구성바 → ③집합·카드 · "
                "나침반은 거시 참고 · 주문은 사람·HTS."
            ),
        ),
    )
    render_screen_market_nav(ctx.root)

    mid_ctx, short_ctx = _pair_mid_short_ctx(ctx)
    if not (mid_ctx.scoreboard_rows or []) and not (short_ctx.scoreboard_rows or []):
        _render_status_card(
            "이 시장 정량이 없습니다. 확인 → ① 중기·단기 정량·정성 한 번에.",
            tone="warn",
        )

    # 0) 오늘 매매·운영 — 무엇을 할지 먼저
    st.markdown(
        _ops_playbook_html(mid_ctx, short_ctx, root=Path(ctx.root)),
        unsafe_allow_html=True,
    )

    # 1) 목표 구성 바
    try:
        from alpha_system.ui.services.alpha_envelope_board import (
            book_slide_bar_html,
            build_book_slide_segments,
        )

        _segs, _sleeves = build_book_slide_segments(
            None,
            root=Path(ctx.root),
            mid_proposal_rows=list(mid_ctx.portfolio_rows or []),
            short_proposal_rows=list(short_ctx.portfolio_rows or []),
        )
        st.markdown(
            book_slide_bar_html(_segs, sleeves=_sleeves),
            unsafe_allow_html=True,
        )
    except Exception:  # noqa: BLE001
        pass
    st.markdown(_ux_read_guide_html(), unsafe_allow_html=True)

    # 2) 중기 — 집합 → 제안 할 일 → 보유 상세
    st.markdown('<div class="pf-tier-1">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="pf-sleeve-h">'
        f'{_esc(copy_get("portfolio", "sleeve_mid", default="중기 · 할 일"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_membership_set_board_html(mid_ctx), unsafe_allow_html=True)
    _render_proposal_book(
        mid_ctx,
        proposal_eligible_sorter=proposal_eligible_sorter,
        proposal_final_sort_label=proposal_final_sort_label,
        section_kicker="중기",
    )
    _render_holdings_book(mid_ctx, section_kicker="중기", show_set_board=False)
    st.markdown("</div>", unsafe_allow_html=True)

    # 3) 단기 — 기본 접기 (위성 보조)
    short_n = len(short_ctx.portfolio_rows or []) + len(
        getattr(short_ctx, "ops_portfolio_rows", None) or []
    )
    short_prop_n = len(short_ctx.portfolio_rows or [])
    with st.expander(
        copy_get(
            "portfolio",
            "sleeve_short_fold",
            default="단기 위성 · 중기 안 볼 때만 · 제안 {n}",
        ).replace("{n}", str(short_prop_n)),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "중기와 다른 장부입니다. 모멘텀·수급으로 짧게 도는 "
                    "위성만 봅니다. 중기 전량·Core 점수는 여기서 바꾸지 않습니다."
                ),
                do_now=(
                    "비어 있으면 접은 채 두세요. 있으면 집합(둘다·제안만·보유만) "
                    "→ 카드 배지만 보고, 예산 카드 %는 ‘단기 풀 전체’ 축소 힌트입니다."
                    if short_n
                    else "단기 제안·보유 없음 · 접어 두고 중기·파킹만 보세요."
                ),
                ignore="중기 목표가 환금·score_m·계좌 % 맞춤 · 단기→중기 전량",
            ),
            unsafe_allow_html=True,
        )
        try:
            _render_short_vol_budget_banner(short_ctx)
        except Exception:  # noqa: BLE001
            pass
        st.markdown(_membership_set_board_html(short_ctx), unsafe_allow_html=True)
        _render_proposal_book(
            short_ctx,
            proposal_eligible_sorter=None,
            proposal_final_sort_label=None,
            section_kicker="단기",
        )
        _render_holdings_book(
            short_ctx, section_kicker="단기", show_set_board=False
        )

    # 4) 입력 — 접힌 후보·컷
    with st.expander(
        copy_get(
            "portfolio",
            "sec_input_fold",
            default="후보·합격선 · 제안 다시 고를 때만",
        ),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "오늘 매매용이 아닙니다. 후보 30·합격선·보유 티커 등록처럼 "
                    "‘무엇을 제안 풀에 넣을지’를 고칠 때만 엽니다."
                ),
                do_now=(
                    "① 보유 티커 체크/업로드 → 집합 대조에 반영 "
                    "② 합격선·편입 수는 토글 켠 뒤 확정(YAML은 확정 전 그대로) "
                    "③ PH-CVS는 관심 종목만"
                ),
                ignore="여기 표로 바로 주문 · 평단·계좌% 필수 입력",
            ),
            unsafe_allow_html=True,
        )
        show_cutoff = st.toggle(
            copy_get(
                "portfolio",
                "input_fold_label",
                default="합격선·편입 수 바꾸기",
            ),
            value=False,
            key=f"pf_show_input_{_book_keys(mid_ctx)}",
            help="중기 합격선·편입 수. 확정 전까지 YAML 그대로.",
        )
        if show_cutoff:
            preview_cutoff, preview_n = _render_cutoff_bar(mid_ctx)
        else:
            preview_cutoff = mid_ctx.cfg.scoring.score_cutoff
            preview_n = int(mid_ctx.cfg.sizing.target_names)
        _render_watch_pool(mid_ctx, preview_cutoff, preview_n)
        _render_phcvs_watch(mid_ctx)


def _verdict_counts(ctx: DashboardContext) -> tuple[int, int, int, int]:
    eligible = list(ctx.portfolio_rows or [])
    blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    prop_tks = {str(getattr(r, "ticker", "") or "").zfill(6) for r in eligible}
    overlap = sum(
        1
        for r in held
        if str(getattr(r, "ticker", "") or "").zfill(6) in prop_tks
    )
    return len(eligible), len(blocked), len(held), overlap


def _row_short_name(row: object) -> str:
    name = str(getattr(row, "name", "") or "").strip()
    tk = str(getattr(row, "ticker", "") or "").zfill(6)
    if name:
        return name if len(name) <= 8 else name[:7] + "…"
    return tk


def _membership_sets(
    ctx: DashboardContext,
) -> tuple[list[str], list[str], list[str], dict[str, object]]:
    prop_rows = list(ctx.portfolio_rows or [])
    held_rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    prop: dict[str, object] = {}
    for r in prop_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if tk.strip("0"):
            prop[tk] = r
    held: dict[str, object] = {}
    for r in held_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if tk.strip("0"):
            held[tk] = r
    both = sorted(set(prop) & set(held))
    prop_only = sorted(set(prop) - set(held))
    held_only = sorted(set(held) - set(prop))
    return both, prop_only, held_only, {**prop, **held}


def _names_join(keys: list[str], src: dict[str, object], *, limit: int = 3) -> str:
    if not keys:
        return "없음"
    bits = [_row_short_name(src[k]) for k in keys[:limit]]
    extra = len(keys) - limit
    if extra > 0:
        bits.append(f"외 {extra}")
    return " · ".join(bits)


def _verdict_todos(ctx: DashboardContext) -> list[str]:
    eligible = list(ctx.portfolio_rows or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    act_n = {"exit_full": 0, "cash_half": 0, "trim": 0, "missing": 0}
    for r in held:
        kind = str(getattr(r, "ops_signal", "") or "")
        if kind in act_n:
            act_n[kind] += 1
    sell_n = len(_holdings_sell_actions(ctx)) if held else 0
    todos: list[str] = []
    if act_n["exit_full"]:
        todos.append(f"전량 Review {act_n['exit_full']}")
    if act_n["cash_half"]:
        todos.append(f"환금 Review {act_n['cash_half']}")
    if act_n["trim"]:
        todos.append(f"줄이기 Review {act_n['trim']}")
    if sell_n and sell_n > (
        act_n["exit_full"] + act_n["cash_half"] + act_n["trim"]
    ):
        todos.append(f"오늘 비중 매도 {sell_n}")
    if act_n["missing"]:
        todos.append(f"목표가 없음 {act_n['missing']}")
    if not eligible:
        todos.append("제안 비어 있음 · Soft/추세·후보 확인")
    return todos


def _economy_stance_line(root: Path) -> tuple[str, str]:
    """(태도 제목, 포트 한 줄). 실패 시 기본."""
    try:
        from alpha_system.economy_compass.stress_overlay import build_bubble_stress_board
        from alpha_system.economy_signal import load_cached_signal
        from alpha_system.ui.services.economy_playbook import stage_playbook

        cached = load_cached_signal(root)
        stress = build_bubble_stress_board(cached)
        stage = (
            stress.posture_stage
            if stress.posture_stage is not None
            else (None if cached is None else cached.stage)
        )
        book = stage_playbook(stage)
        title = book.title or "국면 참고"
        body = " · ".join(c.body for c in book.cards[:2]) if book.cards else ""
        if not body:
            body = "나침반에서 국면 확인 · 종목 주문은 이 포트에서"
        return title, body
    except Exception:  # noqa: BLE001
        return (
            "국면 참고",
            "경제 나침반 = 거시만 · 알파 매매·비중은 이 화면",
        )


def _ops_playbook_html(
    mid_ctx: DashboardContext,
    short_ctx: DashboardContext,
    *,
    root: Path | None = None,
) -> str:
    """오늘 매매 순서 + 구성·나침반 역할 — 포트 최상단."""
    base = Path(root or getattr(mid_ctx, "root", ".") or ".")
    mkt = str(getattr(mid_ctx, "screen_market", None) or "KOSPI")
    both, prop_only, held_only, src = _membership_sets(mid_ctx)
    sell_todos = _verdict_todos(mid_ctx)
    short_todos = [
        f"단기·{t}" if not str(t).startswith("단기") else str(t)
        for t in _verdict_todos(short_ctx)
    ]
    stance_title, stance_body = _economy_stance_line(base)

    sell_n = len(held_only) + sum(
        1
        for t in sell_todos
        if any(k in t for k in ("전량", "환금", "줄이기", "매도"))
    )
    # de-dupe rough count for display
    sell_label = (
        f"보유만 {_names_join(held_only, src)}"
        if held_only
        else ("신호 " + " · ".join(sell_todos[:2]) if sell_todos else "긴급 매도 없음")
    )
    hold_label = (
        f"{_names_join(both, src)} · 배지 확인"
        if both
        else "둘 다 없음 · 보유 티커 등록부터"
    )
    buy_label = (
        f"{_names_join(prop_only, src)} · Soft 통과 · 하루≤33%"
        if prop_only
        else "신규 자리 없음 · 파킹(단기채) 유지"
    )

    steps = (
        f'<div class="pf-ops-step pf-ops-sell">'
        f'<div class="pf-ops-num">1</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">팔기 먼저</div>'
        f'<div class="pf-ops-d">{_esc(sell_label)}</div>'
        f'<div class="pf-ops-hint">전량 → 환금(50%) → 줄이기(25%) · 트레일·목표가 배지</div>'
        f"</div></div>"
        f'<div class="pf-ops-step pf-ops-hold">'
        f'<div class="pf-ops-num">2</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">유지 · 둘 다</div>'
        f'<div class="pf-ops-d">{_esc(hold_label)}</div>'
        f'<div class="pf-ops-hint">제안∩보유 · 추매는 Soft·이평 PASS일 때만</div>'
        f"</div></div>"
        f'<div class="pf-ops-step pf-ops-buy">'
        f'<div class="pf-ops-num">3</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">사기 · 제안만</div>'
        f'<div class="pf-ops-d">{_esc(buy_label)}</div>'
        f'<div class="pf-ops-hint">목표 자리 채우기 · 계좌 % 맞춤 아님 · HTS 회차</div>'
        f"</div></div>"
    )

    detail_bits = sell_todos[:3] + short_todos[:2]
    if not detail_bits:
        detail_bits = ["긴급 액션 없음 · 아래 집합·카드만 Review"]
    detail_html = "".join(
        f'<div class="pf-verdict-todo">{_esc(t)}</div>' for t in detail_bits
    )

    m_el, m_bl, m_he, m_ov = _verdict_counts(mid_ctx)
    s_el, _, s_he, _ = _verdict_counts(short_ctx)

    return (
        '<div class="pf-verdict pf-ops-playbook" role="region" '
        'aria-label="오늘 매매 운영">'
        '<div class="pf-verdict-kicker">오늘 매매 · 운영 순서</div>'
        f'<div class="pf-verdict-title">{_esc(mkt)} · 팔기 → 유지 → 사기</div>'
        '<div class="pf-verdict-scope">'
        "구성=아래 목표바(공격·방어·파킹) · 할 일=집합·카드 · "
        "나침반=거시 참고만 · 자동주문·target 없음"
        "</div>"
        f'<div class="pf-ops-stance">'
        f'<span class="pf-ops-stance-k">나침반 태도</span>'
        f'<span class="pf-ops-stance-t">{_esc(stance_title)}</span>'
        f'<span class="pf-ops-stance-b">{_esc(stance_body)}</span>'
        f"</div>"
        f'<div class="pf-ops-steps">{steps}</div>'
        f'<div class="pf-verdict-grid">'
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">중기 제안</div>'
        f'<div class="pf-verdict-n">{m_el}</div>'
        f'<div class="pf-verdict-s">대기 {m_bl} · 보유 {m_he} · 둘다 {m_ov}</div></div>'
        f'<div class="pf-verdict-cell">'
        f'<div class="pf-verdict-k">팔 Review</div>'
        f'<div class="pf-verdict-n">{len(held_only)}</div>'
        f'<div class="pf-verdict-s">보유만 · 신호 {sell_n}</div></div>'
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">사 Review</div>'
        f'<div class="pf-verdict-n">{len(prop_only)}</div>'
        f'<div class="pf-verdict-s">단기 제안 {s_el} · 단보유 {s_he}</div></div>'
        f"</div>"
        f'<div class="pf-verdict-do">'
        f'<div class="pf-verdict-do-h">신호 메모</div>'
        f"{detail_html}"
        f"</div>"
        "</div>"
    )


def _portfolio_verdict_html(ctx: DashboardContext) -> str:
    """단일 장부 결론(하위 호환·테스트)."""
    short = is_short(getattr(ctx, "screen_horizon", None))
    el, bl, he, ov = _verdict_counts(ctx)
    todos = _verdict_todos(ctx) or ["긴급 액션 없음 · 제안·보유만 Review"]
    book = "단기" if short else "중기"
    mkt = str(getattr(ctx, "screen_market", None) or "KOSPI")
    cells = (
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">최종 제안</div>'
        f'<div class="pf-verdict-n">{el}</div>'
        f'<div class="pf-verdict-s">편입 · 비중은 ③</div></div>'
        f'<div class="pf-verdict-cell pf-verdict-warn">'
        f'<div class="pf-verdict-k">대기</div>'
        f'<div class="pf-verdict-n">{bl}</div>'
        f'<div class="pf-verdict-s">편입하지 않음</div></div>'
        f'<div class="pf-verdict-cell">'
        f'<div class="pf-verdict-k">실보유</div>'
        f'<div class="pf-verdict-n">{he}</div>'
        f'<div class="pf-verdict-s">제안중 {ov}</div></div>'
    )
    todo_html = "".join(
        f'<div class="pf-verdict-todo">{_esc(t)}</div>' for t in todos[:4]
    )
    return (
        '<div class="pf-verdict">'
        '<div class="pf-verdict-kicker">결론 · 무엇을 넣고·빼고·들고 있나</div>'
        f'<div class="pf-verdict-title">{_esc(mkt)} · {_esc(book)}</div>'
        '<div class="pf-verdict-scope">'
        "③ 제안 · ④ 보유가 결정면 · 후보·컷은 아래 입력 · "
        "자동주문·target 기입 없음"
        "</div>"
        f'<div class="pf-verdict-grid">{cells}</div>'
        f'<div class="pf-verdict-do">'
        f'<div class="pf-verdict-do-h">오늘 Review</div>'
        f"{todo_html}"
        f"</div>"
        "</div>"
    )


def _portfolio_verdict_html_unified(
    mid_ctx: DashboardContext,
    short_ctx: DashboardContext,
) -> str:
    """하위 호환 — 통합 운영판과 동일 축."""
    return _ops_playbook_html(
        mid_ctx,
        short_ctx,
        root=Path(getattr(mid_ctx, "root", ".") or "."),
    )


def _fmt_num(val, *, integers: bool = False) -> str:
    if val is None:
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    if integers:
        return f"{int(round(n)):,}"
    return f"{n:.2f}"


def _render_phcvs_watch(ctx: DashboardContext) -> None:
    """PH-CVS detail below ③④ — glance strip already lives in ③ (anti-leak)."""
    from alpha_system.review.phcvs_auto_eval import run_and_write
    from alpha_system.ui.services.phcvs_watch_board import (
        _is_attention,
        load_phcvs_watch,
        phcvs_watch_html,
    )

    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    board = load_phcvs_watch(
        ctx.root,
        proposal_rows=getattr(ctx, "portfolio_rows", None),
        holdings_rows=held,
    )
    title = copy_get("portfolio", "sec_phcvs", default="관심 종목 추적")
    attn_n = sum(1 for r in board.rows if _is_attention(r))
    fold_bits = [title]
    if attn_n:
        fold_bits.append(f"지금 볼 것 {attn_n}")
    else:
        fold_bits.append("평소 안 펴도 됨")
    with st.expander(" · ".join(fold_bits), expanded=False):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "후보·제안에 올린 관심 종목의 추가 점검입니다. "
                    "오늘 팔→유지→사 순서를 바꾸지 않습니다."
                ),
                do_now=(
                    f"빨간 ‘지금 볼 것’ {attn_n}건만 보면 됨"
                    if attn_n
                    else "즉시 볼 것 없음 · 접어 두세요."
                ),
                ignore="여기 표로 자동 매수·편입 · 현금=시드 혼동",
            ),
            unsafe_allow_html=True,
        )
        chips: list[tuple[str, str]] = []
        if attn_n:
            chips.append((f"지금 볼 것 {attn_n}", "warn"))
        else:
            chips.append(("즉시 Review 없음", "muted"))
        if board.as_of_prices:
            chips.append((f"가격 {board.as_of_prices}", "muted"))
        chips.append(("Review-only", "muted"))
        _render_section_head(
            title,
            summary=copy_get(
                "portfolio",
                "phcvs_caption",
                default="상세·재평가만 · 매수·자동편입 없음",
            ),
            chips=chips,
            tier="input",
        )
        rerun = st.button(
            copy_get("portfolio", "phcvs_reeval", default="다시 평가"),
            key="phcvs_auto_reeval",
            help=copy_get(
                "portfolio",
                "phcvs_reeval_help",
                default=(
                    "prices.csv 기준 S00/S03·유동성 재계산. "
                    "target_portfolio·QVM 순위는 변경하지 않습니다."
                ),
            ),
        )
        if rerun:
            try:
                watch_path, snap_path = run_and_write(Path(ctx.root))
                st.success(
                    copy_get(
                        "portfolio",
                        "phcvs_reeval_ok",
                        default="PH-CVS 자동평가 완료 (watch·snapshot만 갱신).",
                    )
                    + f" · {watch_path.name} · {snap_path.name}"
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001 — surface to operator
                st.error(f"PH-CVS 자동평가 실패: {exc}")
        # Attention already on ③ glance — detail cards only here.
        st.markdown(
            phcvs_watch_html(board, include_attention=False),
            unsafe_allow_html=True,
        )


def _observation_pool_tickers(ctx: DashboardContext, *, band_max: int) -> list[str]:
    """Candidate watch board tickers only — not the full scoreboard universe."""
    from alpha_system.ui.services.rank_watchboard import build_rank_watchboard

    saved = _saved_kr_alpha_rows(ctx)
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers={str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])},
        held_tickers={str(r["ticker"]) for r in saved},
        proposal_band_max=max(1, int(band_max)),
        max_rows=watch_max(
            getattr(ctx, "screen_market", None),
            getattr(ctx, "screen_horizon", None),
        ),
    )
    return [str(r.ticker).zfill(6) for r in board.rows]


def _render_proposal_opendart_gates(ctx: DashboardContext) -> None:
    """OpenDART on the watch pool: 경영참여 게이트 + 최대주주 + Review-only 선행 트리거."""
    from alpha_system.ui.services.cecs_opendart_pack import (
        estimate_watch_calls,
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )
    from alpha_system.ui.services.dart_quota import load_quota

    band = int(getattr(ctx.cfg.sizing, "target_names", 6) or 6)
    tickers = _observation_pool_tickers(ctx, band_max=band)
    proposal_rows = list(ctx.portfolio_rows or [])
    if not tickers and not proposal_rows:
        return
    if not tickers:
        tickers = [str(r.ticker).zfill(6) for r in proposal_rows]
    names = {
        str(r.ticker).zfill(6): (r.name or r.ticker)
        for r in list(ctx.scoreboard_rows or []) + proposal_rows
    }
    journal = ctx.root / "data" / "alpha_system_journal.jsonl"
    as_of = ctx.as_of if isinstance(ctx.as_of, _date) else _date.today()
    data_dir = _source_dir(ctx)
    from alpha_system.ui.services.opendart_evidence_board import (
        opendart_evidence_html,
        opendart_gates_html,
        opendart_join_html,
        opendart_toolbar_html,
        parse_evidence_board,
    )
    # opendart_gates_html: detail expander only (join has 게이트 병합)
    from alpha_system.ui.services.dart_evidence import (
        evidence_gate_policy_path,
        load_evidence_gate_policy,
        withdrawn_buyback_gate_candidates,
    )
    from alpha_system.shadow.evidence_ab import evidence_ab_report

    snap = load_opendart_watch(ctx.root, data_dir=data_dir)
    need = watch_needs_refresh(snap, tickers)
    quota = load_quota(Path(data_dir))
    policy = load_evidence_gate_policy(evidence_gate_policy_path(Path(data_dir)))
    gate_on = bool(policy.get("enabled"))

    # First-ever: rebuild from disk caches only (0 calls). Network only on button.
    if snap is None:
        try:
            snap = refresh_opendart_proposal_watch(
                ctx.root,
                tickers,
                as_of=as_of,
                journal_path=journal,
                data_dir=data_dir,
                mode="cache_only",
            )
        except Exception as exc:
            st.warning(f"OpenDART 캐시 로드 실패: {exc}")

    st.markdown(
        opendart_toolbar_html(
            quota_line=quota.status_line(),
            stale=need,
            as_of=str(getattr(snap, "as_of", "") or ""),
            fetched_at=str(getattr(snap, "fetched_at", "") or ""),
            gate_mode_on=gate_on,
        ),
        unsafe_allow_html=True,
    )
    # 중기·단기 한 페이지 → 위젯 key에 장부 접미사 필수
    bk = _book_keys(ctx)
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    with r1c1:
        do_incr = st.button(
            copy_get("portfolio", "opendart_btn_incremental", default="증분 갱신"),
            key=f"pf_od_incr_{bk}",
            help=f"예상 상한 ≈{estimate_watch_calls(len(tickers))}회(실제는 만료분만)",
            use_container_width=True,
        )
    with r1c2:
        do_force = st.button(
            copy_get("portfolio", "opendart_btn_force", default="전체 재탐색(위험)"),
            key=f"pf_od_force_{bk}",
            use_container_width=True,
        )
    with r2c1:
        do_cache = st.button(
            copy_get("portfolio", "opendart_btn_cache", default="캐시만 다시 그리기"),
            key=f"pf_od_cache_{bk}",
            use_container_width=True,
        )
    with r2c2:
        do_deep = st.button(
            copy_get("portfolio", "screen_deep_btn", default="심층 다시 그리기"),
            key=f"pf_screen_deep_{bk}",
            help="관찰·제안 풀 심층 재평가 (DART 0회 · 점수 불변)",
            use_container_width=True,
        )
    if do_incr or do_force or do_cache:
        mode = "incremental" if do_incr else ("force" if do_force else "cache_only")
        try:
            with st.spinner("OpenDART 갱신 중…"):
                snap = refresh_opendart_proposal_watch(
                    ctx.root,
                    tickers,
                    as_of=as_of,
                    journal_path=journal,
                    data_dir=data_dir,
                    mode=mode,
                    enrich_documents=(mode == "incremental"),
                    max_document_fetches=12,
                )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            return
    if snap is None:
        return
    if snap.missing_key:
        st.warning("Open DART API 키가 없습니다. 설정에 키를 넣은 뒤 증분 갱신하세요.")

    flags = list(snap.flag_models())
    path = overlay_path(_source_dir(ctx))
    overlay = load_qual_overlay(path)
    if flags:
        updated, applied = apply_opendart_flag_gates(overlay, flags, as_of=as_of)
        if applied:
            save_qual_overlay(path, updated)
            overlay = updated
            for tk in applied:
                journal_overlay_change(
                    action_kind="QUAL_GATE",
                    subject=tk,
                    rationale="OpenDART 경영참여·연기금 자동 제외",
                    as_of=as_of,
                    payload={"source": "opendart_watch", "tickers": list(applied)},
                    journal_path=journal,
                )
            st.rerun()
    gated = overlay.gated_tickers()

    board = parse_evidence_board(getattr(snap, "evidence", None) or [])
    blocked_rows = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    gate_cands = withdrawn_buyback_gate_candidates(board)
    ab = None
    if gate_cands:
        prop_tks = [str(r.ticker).zfill(6) for r in proposal_rows]
        score_map = {
            str(r.ticker).zfill(6): float(getattr(r, "total_score", 0) or 0)
            for r in list(ctx.scoreboard_rows or [])
            if getattr(r, "ticker", None)
        }
        ab = evidence_ab_report(
            prop_tks or [b.ticker for b in board],
            [tk for tk, _ in gate_cands],
            score_by_ticker=score_map,
        )
    # Screen-pool PH-CVS-style verify (not PDF 7 names) — same glance as proposal.
    from alpha_system.review.screen_deep_verify import (
        MODEL_VERSION as SCREEN_DEEP_MODEL,
        build_screen_verify,
        load_screen_verify,
        save_screen_verify,
        screen_verify_attention_html,
    )
    sv_board = load_screen_verify(Path(data_dir))
    want_tks = list(
        dict.fromkeys(
            tickers
            + [str(r.ticker).zfill(6) for r in proposal_rows]
            + [str(r.ticker).zfill(6) for r in blocked_rows]
        )
    )
    if (
        do_deep
        or not sv_board.available
        or sv_board.model_version != SCREEN_DEEP_MODEL
        or {r.ticker for r in sv_board.rows} != set(want_tks)
    ):
        try:
            sv_board = build_screen_verify(
                ctx.root,
                data_dir=Path(data_dir),
                tickers=want_tks,
                names=names,
                proposal_tickers=[str(r.ticker).zfill(6) for r in proposal_rows],
                blocked_tickers=[str(r.ticker).zfill(6) for r in blocked_rows],
                opendart_watch={
                    "evidence": list(getattr(snap, "evidence", None) or []),
                    "flags": list(getattr(snap, "flags", None) or []),
                    "metrics": list(getattr(snap, "metrics", None) or []),
                },
                min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
                as_of=str(getattr(snap, "as_of", "") or as_of.isoformat()),
            )
            save_screen_verify(Path(data_dir), sv_board)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"스크린 심층 검증 실패: {exc}")
    attn = screen_verify_attention_html(sv_board)
    if attn:
        st.markdown(attn, unsafe_allow_html=True)
    for r in sv_board.rows:
        if r.ticker and r.ticker not in names:
            names[r.ticker] = r.name or r.ticker
    # One glance table — PDF-7 PH-CVS stays in bottom expander only.
    st.markdown(
        opendart_join_html(
            proposal_rows=proposal_rows,
            blocked_rows=blocked_rows,
            scoreboard_rows=list(ctx.scoreboard_rows or []),
            board=board,
            flags=flags,
            gated=set(gated),
            names=names,
            screen_verify_rows=list(sv_board.rows),
        ),
        unsafe_allow_html=True,
    )
    with st.expander("상세 · 게이트 메모 · 공시 건별", expanded=False):
        if flags:
            st.markdown(
                opendart_gates_html(flags, names=names, gated=set(gated)),
                unsafe_allow_html=True,
            )
        st.markdown(
            opendart_evidence_html(
                board,
                names=names,
                withdrawn_tickers=[tk for tk, _ in gate_cands],
                ab=ab,
                gate_mode_on=gate_on,
                show_attn=False,
            ),
            unsafe_allow_html=True,
        )

    if (
        gate_on
        and policy.get("exclude_withdrawn_buyback", True)
        and gate_cands
    ):
        updated, applied = apply_evidence_withdrawn_gates(
            overlay, gate_cands, as_of=as_of
        )
        if applied:
            save_qual_overlay(path, updated)
            for tk in applied:
                journal_overlay_change(
                    action_kind="QUAL_GATE",
                    subject=tk,
                    rationale="증거 게이트: 자사주 체인 최종 철회",
                    as_of=as_of,
                    payload={"source": "evidence_withdrawn", "tickers": list(applied)},
                    journal_path=journal,
                )
            st.info(
                copy_get(
                    "portfolio",
                    "opendart_evidence_gated",
                    default="증거 게이트 ON · 자사주 철회 {n}종 제안 제외(점수 불변).",
                    n=len(applied),
                )
            )
            st.rerun()


def _render_proposal_target_board(ctx: DashboardContext) -> None:
    """Justified P/B auto-apply on the confirmed book → exit YAML only."""
    rows = list(ctx.portfolio_rows or [])
    if not rows:
        return
    from alpha_system.ui.services.weekly_domain_gates import auto_apply_proposal_quant_targets

    as_of = ctx.as_of if isinstance(ctx.as_of, _date) else _date.today()
    journal = ctx.root / "data" / "alpha_system_journal.jsonl"
    result = auto_apply_proposal_quant_targets(
        root=ctx.root,
        rows=rows,
        as_of=as_of,
        journal_path=journal,
    )
    if result.get("applied"):
        st.rerun()

    skipped = list(result.get("skipped") or [])
    if skipped:
        st.warning(f"정량 초안 불가 (ROE·PBR·섹터 부족): {', '.join(skipped)} · 편입 차단")


def _esc_pf(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _chips_html(chips: list[tuple[str, str]] | None) -> str:
    if not chips:
        return ""
    bits = [
        f'<span class="pf-sec-chip pf-sec-chip-{_esc_pf(tone)}">{_esc_pf(label)}</span>'
        for label, tone in chips
    ]
    return f'<div class="pf-sec-chips">{"".join(bits)}</div>'


def _render_section_head(
    title: str,
    *,
    summary: str = "",
    chips: list[tuple[str, str]] | None = None,
    extra_html: str = "",
    tier: str = "",
) -> None:
    """Section header inside the outer container (no nested outer frame)."""
    summary_html = (
        f'<div class="pf-sec-summary">{_esc_pf(summary)}</div>' if summary else ""
    )
    tier_cls = f" pf-sec-head-{_esc_pf(tier)}" if tier else ""
    st.markdown(
        f'<div class="pf-sec-head{tier_cls}">'
        f'<div class="pf-sec-title">{_esc_pf(title)}</div>'
        f"{summary_html}{_chips_html(chips)}{extra_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_control_card(label: str, *, hint: str = "") -> None:
    """Control label row inside the section (not a separate box)."""
    hint_html = (
        f'<span class="pf-ctl-hint">{_esc_pf(hint)}</span>' if hint else ""
    )
    st.markdown(
        f'<div class="pf-ctl-row">'
        f'<span class="pf-ctl-label">{_esc_pf(label)}</span>'
        f"{hint_html}</div>",
        unsafe_allow_html=True,
    )


def _render_status_card(body: str, *, tone: str = "muted") -> None:
    st.markdown(
        f'<div class="pf-status pf-status-{_esc_pf(tone)}">'
        f"{_esc_pf(body)}</div>",
        unsafe_allow_html=True,
    )


def _proposal_map_html(
    *,
    short: bool,
    quality_sort: bool,
    n_eligible: int,
    n_blocked: int,
    n_held: int,
) -> str:
    if short:
        tiles = [
            ("사도 됨", str(n_eligible), "단기 편입", "모멘텀 Soft 통과", "ok"),
            ("지금은 안 삼", str(n_blocked), "대기·제외", "조건 미달 · 비중 0", "warn"),
            ("단기 보유", str(n_held), "이미 든 것", "유지·축소·교체", "muted"),
        ]
        if n_eligible == 0 and n_blocked > 0:
            yolk = (
                f"편입 0 · 대기 {n_blocked} = 단기 Soft/게이트로 막힘 · "
                "오늘은 중기·파킹만 · 대기 종목 신규 매수 금지"
            )
        elif n_eligible == 0:
            yolk = "단기 편입 없음 · 접어 두고 중기만 봐도 됨"
        else:
            yolk = "단기=위성 · 중기 QVM과 섞지 않음 · 하루≤33% · 사람만 주문"
    else:
        tiles = [
            ("사도 됨", str(n_eligible), "중기 편입", "목표 자리·카드", "ok"),
            ("지금은 안 삼", str(n_blocked), "노른자 대기", "비싸거나 게이트", "warn"),
            ("중기 보유", str(n_held), "이미 든 것", "집합 대조와 다를 수 있음", "muted"),
        ]
        yolk = (
            "대기(노른자)=고Q인데 지금은 안 삼 · "
            "보유 전부 ≠ 노른자 · 매매 순서는 맨 위「오늘 매매」"
        )
        if quality_sort:
            yolk = "편입 목록 Q↓·하케다카↓ · " + yolk
    cells = "".join(
        f'<div class="pf-map-cell pf-map-{tone}">'
        f'<div class="pf-map-k">{_esc_pf(k)}</div>'
        f'<div class="pf-map-n">{_esc_pf(n)}</div>'
        f'<div class="pf-map-tag">{_esc_pf(tag)}</div>'
        f'<div class="pf-map-body">{_esc_pf(body)}</div>'
        f"</div>"
        for k, n, tag, body, tone in tiles
    )
    note = (
        f'<div class="pf-map-note">{_esc_pf(yolk)}</div>' if yolk else ""
    )
    return f'<div class="pf-map">{cells}</div>{note}'


def _proposal_empty_message(
    *,
    short: bool,
    n_blocked: int,
) -> str:
    if short and n_blocked > 0:
        return copy_get(
            "portfolio",
            "proposal_final_empty_short_blocked",
            default=(
                "단기 편입 0종 · 아래 대기 {n}은 Soft/게이트로 막혀 "
                "지금은 사지 않습니다. 접어 두고 중기·파킹만 보세요. "
                "합격선 고장이 아닙니다."
            ),
            n=n_blocked,
        )
    if short:
        return copy_get(
            "portfolio",
            "proposal_final_empty_short",
            default=(
                "단기 편입 후보 없음 · 정량을 안 돌렸거나 Soft 통과분이 없습니다. "
                "중기만 운영해도 됩니다."
            ),
        )
    if n_blocked > 0:
        return copy_get(
            "portfolio",
            "proposal_final_empty_blocked",
            default=(
                "중기 편입 0종 · 아래 대기 {n}은 게이트·목표가 등으로 제외. "
                "대기=비중 없음 · 사람만 Review."
            ),
            n=n_blocked,
        )
    return copy_get(
        "portfolio",
        "proposal_final_empty",
        default="편입 후보 없음 · 확인에서 정량 후 후보·합격선을 보세요.",
    )


def _holdings_sell_actions(ctx: DashboardContext) -> list:
    """Ops rows with stance=매도, priority-sorted (strongest first)."""
    try:
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
        from alpha_system.ui.services.weight_action import build_weight_actions_for_rows
    except Exception:  # noqa: BLE001
        return []
    rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    if not rows:
        return []
    flow_data_dir = Path(
        getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
    )
    try:
        chart_map = reads_by_ticker(ctx)
    except Exception:  # noqa: BLE001
        chart_map = {}
    try:
        pairs = build_weight_actions_for_rows(
            rows, chart_map=chart_map, flow_data_dir=flow_data_dir
        )
    except Exception:  # noqa: BLE001
        return []
    sells = [(r, a) for r, a in pairs if a.stance == "매도"]
    sells.sort(key=lambda t: (t[1].priority, -(t[1].move_pct or 0)))
    return sells


def _holdings_sell_pressure(ctx: DashboardContext) -> bool:
    return bool(_holdings_sell_actions(ctx))


def _render_next_buy_queue(ctx: DashboardContext) -> None:
    """중기 「다음 순매수」— 오늘 비중 아래. A→B Review 한 줄. 단기 스킵."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    try:
        from alpha_system.ui.services.next_buy_queue import (
            build_next_buy_queue,
            enrich_scoreboard_prices,
            format_rotation_ab_hint,
            next_buy_board_html,
        )
    except Exception:  # noqa: BLE001
        return
    scoreboard = list(getattr(ctx, "scoreboard_rows", None) or [])
    if not scoreboard:
        return
    proposal = list(getattr(ctx, "portfolio_rows", None) or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    enriched = enrich_scoreboard_prices(scoreboard, proposal, held, blocked)
    sells = _holdings_sell_actions(ctx)
    sell_pressure = bool(sells)
    ma_map: dict[str, str] = {}
    try:
        from alpha_system.proposal_chart import load_cached_charts, norm_ticker as _nt

        board = load_cached_charts(Path(ctx.root), str(getattr(ctx, "market", "KOSPI") or "KOSPI"))
        if board is not None:
            for it in board.items or []:
                lab = str(getattr(it, "ma_label", "") or "")
                tk = _nt(getattr(it, "ticker", ""))
                if tk and lab:
                    ma_map[tk] = lab
    except Exception:  # noqa: BLE001
        ma_map = {}
    queue = build_next_buy_queue(
        scoreboard=enriched,
        proposal_rows=proposal,
        held_rows=held,
        sell_pressure=sell_pressure,
        top_k=8,
        exclude_proposal=True,
        ma_label_by_ticker=ma_map or None,
    )
    rotation_hint = ""
    if sell_pressure:
        row_a, act_a = sells[0]
        buy_b = queue.items[0] if queue.items else None
        rotation_hint = format_rotation_ab_hint(
            sell_name=str(getattr(row_a, "name", "") or ""),
            sell_ticker=str(getattr(row_a, "ticker", "") or ""),
            sell_pct=float(act_a.move_pct or 0),
            buy=buy_b,
            buy_cum_cap=67.0,
            day_cap=33.0,
        )
    title = copy_get("portfolio", "next_buy_title", default="다음 순매수")
    legend = copy_get(
        "portfolio",
        "next_buy_legend",
        default="제안 N 유지 · 미보유·목표가↓ · 점수순 · Review-only · target 불변",
    )
    sell_hint = copy_get(
        "portfolio",
        "next_buy_sell_hint",
        default="여유·교체 검토 · 상위부터 무릎 매수 Review · 자동주문 없음",
    )
    st.markdown(
        next_buy_board_html(
            queue,
            title=title,
            legend=legend,
            sell_hint=sell_hint,
            rotation_hint=rotation_hint,
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "portfolio",
            "next_buy_caption",
            default=(
                "매도 시 순환 Review(A→B) · B 오늘≤33% · 잔여 현금/단기채 · "
                "제안 N 유지 · 사람만 · docs/ROTATION_A_TO_B_RULE"
            ),
        )
    )


def _render_proposal_book(
    ctx: DashboardContext,
    *,
    proposal_eligible_sorter: Callable[
        [list[PortfolioRow], DashboardContext], list[PortfolioRow]
    ]
    | None = None,
    proposal_final_sort_label: str | None = None,
    section_kicker: str | None = None,
) -> None:
    short = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        eligible = list(ctx.portfolio_rows or [])
        if proposal_eligible_sorter and eligible:
            eligible = proposal_eligible_sorter(eligible, ctx)
        blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
        held_n = len(getattr(ctx, "ops_portfolio_rows", None) or [])
        if short:
            sec_title = copy_get(
                "portfolio", "sec_proposal_short", default="단기 제안"
            )
            summary = copy_get(
                "portfolio",
                "screen_book_caption_short",
                default=(
                    "위성만 · 중기와 섞지 않음 · 편입=사도 됨 · "
                    "대기=지금은 안 삼 · 사람만 주문"
                ),
            )
        else:
            sec_title = copy_get(
                "portfolio", "sec_proposal", default="제안 · 할 일"
            )
            if section_kicker:
                sec_title = f"{section_kicker} · {sec_title}"
            summary = copy_get(
                "portfolio",
                "screen_book_caption",
                default=(
                    "편입=사도 됨 · 대기=지금은 안 삼 · "
                    "카드=Review · 사람만 주문"
                ),
            )
        _render_section_head(
            sec_title,
            summary=summary,
            chips=[
                (f"사도 됨 {len(eligible)}", "ok"),
                (f"안 삼 {len(blocked)}", "warn"),
            ],
            tier="primary",
            extra_html=_proposal_map_html(
                short=short,
                quality_sort=bool(proposal_final_sort_label),
                n_eligible=len(eligible),
                n_blocked=len(blocked),
                n_held=held_n,
            ),
        )
        if short and not eligible:
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "단기 위성 제안 칸입니다. 중기 Core·목표가 환금과 "
                        "다른 장부입니다."
                    ),
                    do_now=(
                        f"편입 0 · 대기 {len(blocked)} → 단기 신규는 쉬고 "
                        "중기·파킹만. 대기 목록은 ‘왜 막혔는지’ 참고용."
                        if blocked
                        else "단기 후보 없음 · 이 접기 닫고 중기만 보세요."
                    ),
                    ignore="합격선 고장으로 단정 · 대기 종목 추격 매수 · 중기 전량",
                ),
                unsafe_allow_html=True,
            )
        with st.expander(
            copy_get(
                "portfolio",
                "sec_proposal_evidence_short" if short else "sec_proposal_evidence",
                default=(
                    "왜 막혔는지 · 섹터·게이트 (평소 안 펴도 됨)"
                    if short
                    else "근거 · 섹터·게이트·목표가"
                ),
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose="편입/대기 숫자 아래의 기술 근거만 모았습니다.",
                    do_now="궁금한 게이트·섹터만 · 매매 순서는 맨 위「오늘 매매」.",
                    ignore="여기 표로 자동매도·target 기입",
                ),
                unsafe_allow_html=True,
            )
            _render_sector_exposure(ctx)
            _render_revalidate_flags(ctx)
            _render_proposal_opendart_gates(ctx)
            if not short:
                _render_proposal_target_board(ctx)
            else:
                st.caption(
                    copy_get(
                        "portfolio",
                        "ops_cue_short_caption",
                        default=(
                            "단기 배지: 제안 밖·모멘텀 붕괴=교체 · "
                            "약화=축소 · 중기 목표가 미사용 · 자동매도 없음"
                        ),
                    )
                )
        final_heading = copy_get(
            "portfolio",
            "proposal_final_heading_short" if short else "proposal_final_heading",
            default="사도 되는 단기" if short else "편입 · 목표 자리",
        )
        if proposal_final_sort_label and not short:
            final_heading = f"{final_heading} · {proposal_final_sort_label}"
        st.markdown(
            f'<div class="pf-group-kicker">'
            f'<span class="pf-group-badge pf-group-ok">편입</span> '
            f"{final_heading}"
            f" · {len(eligible)}"
            f"</div>",
            unsafe_allow_html=True,
        )
        if eligible:
            from alpha_system.ui.services.proposal_chart_board import render_proposal_chart_refresh

            render_proposal_chart_refresh(ctx, eligible)
        if not eligible:
            st.info(
                _proposal_empty_message(short=short, n_blocked=len(blocked))
            )
        else:
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix=f"pf_proposal_{_book_keys(ctx)}",
                rows=eligible,
                always_open=True,
            )
        if blocked:
            blocked_head = copy_get(
                "portfolio",
                "proposal_blocked_heading_short" if short else "proposal_blocked_heading",
                default="지금은 안 사는 단기" if short else "편입하지 않음",
            )
            if not short:
                blocked_head = f"{blocked_head} · 노른자 대기"
            st.markdown(
                f'<div class="pf-group-kicker">'
                f'<span class="pf-group-badge pf-group-warn">대기</span> '
                f"{blocked_head}"
                f" · {len(blocked)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                copy_get(
                    "portfolio",
                    "proposal_blocked_caption_short" if short else "proposal_blocked_caption",
                    default=(
                        "모멘텀 Soft·게이트 미달 · 비중 없음 · 추격 매수 금지"
                        if short
                        else "점수 상위이나 지금은 편입 안 함 · 비중 없음"
                    ),
                )
            )
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix=f"pf_blocked_{_book_keys(ctx)}",
                rows=blocked,
            )


def _ux_read_guide_html() -> str:
    """구성·운영 읽는 법."""
    return (
        '<div class="pf-ux-guide" role="note">'
        '<span class="pf-ux-g"><b>구성</b> 목표바=공격·방어·파킹 · 계좌% 아님</span>'
        '<span class="pf-ux-g"><b>운영</b> 위 1→2→3 순서 · 배지대로 수량</span>'
        '<span class="pf-ux-g"><b>집합</b> 둘다=유지 · 제안만=사 · 보유만=팔</span>'
        '<span class="pf-ux-g"><b>나침반</b> 거시 태도만 · 종목 주문은 여기</span>'
        '<span class="pf-ux-g"><b>주문</b> HTS 회차 · 사람만 · target 불변</span>'
        '<span class="pf-ux-g"><b>접기</b> 평소 안 펴도 됨 · 펼치면 맨 위「이 칸」안내부터</span>'
        "</div>"
    )


def _fold_lead_html(
    *,
    purpose: str,
    do_now: str,
    ignore: str = "",
) -> str:
    """접기 본문 맨 위 — 왜 있는지 / 지금 / 무시."""
    ignore_html = (
        f'<div class="pf-fold-row pf-fold-ignore">'
        f'<span class="pf-fold-lab">무시</span>'
        f"<span>{_esc(ignore)}</span></div>"
        if ignore
        else ""
    )
    return (
        '<div class="pf-fold-lead" role="note">'
        f'<div class="pf-fold-row">'
        f'<span class="pf-fold-lab">이 칸</span>'
        f"<span>{_esc(purpose)}</span></div>"
        f'<div class="pf-fold-row pf-fold-do">'
        f'<span class="pf-fold-lab">지금</span>'
        f"<span>{_esc(do_now)}</span></div>"
        f"{ignore_html}"
        "</div>"
    )


def _fold_block_html(title: str, blurb: str) -> str:
    """접기 안 소절 제목."""
    return (
        f'<div class="pf-fold-block">'
        f'<div class="pf-fold-block-h">{_esc(title)}</div>'
        f'<div class="pf-fold-block-b">{_esc(blurb)}</div>'
        f"</div>"
    )


def _membership_set_board_html(
    ctx: DashboardContext,
) -> str:
    """제안∩보유 / 제안만 / 보유만 — 티커 집합 대조 (평단·% 불필요)."""
    both, prop_only, held_only, src = _membership_sets(ctx)
    prop = {
        k: src[k]
        for k in list(prop_only) + list(both)
        if k in src
    }
    held = {
        k: src[k]
        for k in list(held_only) + list(both)
        if k in src
    }

    def _cell(tk: str, row: object) -> str:
        name = str(getattr(row, "name", "") or tk).strip() or tk
        short = name if len(name) <= 8 else name[:7] + "…"
        return (
            f'<span class="pf-set-chip" title="{_esc(name)} ({_esc(tk)})">'
            f"{_esc(short)}</span>"
        )

    def _col(
        title: str,
        todo: str,
        keys: list[str],
        bag: dict[str, object],
        tone: str,
    ) -> str:
        chips = "".join(_cell(k, bag[k]) for k in keys if k in bag) or (
            '<span class="pf-set-empty">없음</span>'
        )
        return (
            f'<div class="pf-set-col pf-set-{_esc(tone)}">'
            f'<div class="pf-set-h">{_esc(title)} · {len(keys)}</div>'
            f'<div class="pf-set-todo">{_esc(todo)}</div>'
            f'<div class="pf-set-chips">{chips}</div>'
            f"</div>"
        )

    return (
        '<div class="pf-set-board" role="group" '
        'aria-label="제안과 보유 집합 대조">'
        '<div class="pf-set-kicker">'
        "종목 할 일 · 집합 대조 · 평단·보유% 없이 운영"
        "</div>"
        '<div class="pf-set-grid">'
        + _col(
            "둘 다",
            "유지 · Soft PASS면 추매 Review",
            both,
            src,
            "ok",
        )
        + _col(
            "제안만",
            "신규 매수 Review · 하루≤33% · HTS",
            prop_only,
            prop,
            "buy",
        )
        + _col(
            "보유만",
            "정리·축소·환금 Review · 먼저 처리",
            held_only,
            held,
            "sell",
        )
        + "</div>"
        '<div class="pf-set-tip">'
        "운영=집합 열 따라 · 금액은 HTS · 목표바 %로 계좌 맞추지 않음 · "
        "자동주문·target 불변"
        "</div>"
        "</div>"
    )


def _render_holdings_book(
    ctx: DashboardContext,
    *,
    section_kicker: str | None = None,
    show_set_board: bool = True,
) -> None:
    short = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        held_rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        prop_tks = {
            str(getattr(r, "ticker", "") or "").zfill(6)
            for r in (ctx.portfolio_rows or [])
        }
        overlap_n = sum(
            1
            for r in held_rows
            if str(getattr(r, "ticker", "") or "").zfill(6) in prop_tks
        )
        hold_chips: list[tuple[str, str]] = [
            (f"보유 티커 {len(held_rows)}", "muted"),
            (f"둘 다 {overlap_n}", "ok"),
            (
                f"제안만 {max(0, len(prop_tks) - overlap_n)}",
                "warn",
            ),
        ]
        sec_title = copy_get("portfolio", "sec_holdings", default="보유 · 보조")
        if section_kicker:
            sec_title = f"{section_kicker} · {sec_title}"
        _render_section_head(
            sec_title,
            summary=copy_get(
                "portfolio",
                "holdings_caption_short" if short else "holdings_caption",
                default="집합은 위 · 여기는 Shadow·상세(접기) · 평단·% 없음",
            ),
            chips=hold_chips,
            tier="primary",
        )
        if show_set_board:
            st.markdown(_membership_set_board_html(ctx), unsafe_allow_html=True)
        _render_weight_action_board(ctx)
        with st.expander(
            copy_get(
                "portfolio",
                "holdings_extra_fold",
                default="심화 참고 · 평소엔 안 펴도 됨",
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "맨 위「오늘 매매」·집합으로 부족한 보조만 모았습니다. "
                        "여기 문장이 매매 순서를 뒤집지 않습니다."
                    ),
                    do_now=(
                        "필요할 칸만: 거시 태도 한 줄 → 다음 살 후보 → "
                        "보유 카드 상세. Shadow·급락 이력은 궁금할 때만."
                    ),
                    ignore=(
                        "가상 손익 KPI · L3 버튼 · Soft 전문 용어 · "
                        "target 자동 기입"
                    ),
                ),
                unsafe_allow_html=True,
            )
            if not short:
                st.markdown(
                    _fold_block_html(
                        "A. 거시 태도",
                        "나침반과 같은 Soft · 줄임/늘림 힌트만 · 종목 배지보다 약함",
                    ),
                    unsafe_allow_html=True,
                )
                _render_stance_decision(ctx)
            _render_monthly_rebal_note(ctx)
            if not short:
                st.markdown(
                    _fold_block_html(
                        "B. 다음 살 후보",
                        "매도 여유 생기면 볼 대기열 · 오늘 바로 올인 아님 · ≤33%",
                    ),
                    unsafe_allow_html=True,
                )
                _render_next_buy_queue(ctx)
                st.markdown(
                    _fold_block_html(
                        "C. 가상 손익 (연습장)",
                        "실제 계좌 아님 · 사이드바 백테스트와 같은 계열 · 주문 지시 없음",
                    ),
                    unsafe_allow_html=True,
                )
                _render_shadow_profit_card(ctx)
                st.markdown(
                    _fold_block_html(
                        "D. 급락 이력",
                        "과거 C1–C3 참고 · 버튼 눌러야 계산 · 전량 강제 아님",
                    ),
                    unsafe_allow_html=True,
                )
                _render_l3_history_review(ctx)
            st.markdown(
                _fold_block_html(
                    "E. 보유 카드 상세",
                    "종목별 배지·근거 · 할 일은 왼쪽 배지(유지/줄이기/환금/전량)",
                ),
                unsafe_allow_html=True,
            )
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix=f"pf_ops_{_book_keys(ctx)}",
                rows=list(ctx.ops_portfolio_rows or []),
                empty_hint=(
                    "실보유 티커 없음 · 후보「보유」체크 또는 티커 업로드"
                ),
            )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_weight_action_board(ctx: DashboardContext) -> None:
    """회차 슬라이드 — 평가액이 있을 때만. 티커만 등록이면 집합 보드만."""
    try:
        rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        if not rows:
            return
        value_sum = 0.0
        for r in rows:
            try:
                value_sum += float(r.weight_pct or 0)
            except (TypeError, ValueError):
                pass
        # 멤버십만(평가액·비중 없음)이면 비중 보드 생략
        if value_sum < 0.5:
            st.caption(
                copy_get(
                    "portfolio",
                    "membership_only_caption",
                    default=(
                        "보유=티커만 등록됨 · 평단·% 없이 집합 대조로 Review · "
                        "회차 금액은 HTS"
                    ),
                )
            )
            return
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
        from alpha_system.ui.services.weight_action import (
            board_items,
            build_weight_actions_for_rows,
            weight_action_board_html,
        )

        flow_data_dir = Path(
            getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
        )
        try:
            chart_map = reads_by_ticker(ctx)
        except Exception:  # noqa: BLE001 — board must not break holdings
            chart_map = {}
        pairs = build_weight_actions_for_rows(
            rows,
            chart_map=chart_map,
            flow_data_dir=flow_data_dir,
        )
        from alpha_system.ui.services.today_port_projection import (
            port_weight_plan_html,
            project_portfolio_after_today,
        )

        with st.expander(
            copy_get(
                "portfolio",
                "today_weight_detail",
                default="회차 금액 참고 · 평가액 있을 때만",
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "종목 자리=100으로 둔 ‘오늘 얼마’ 참고표입니다. "
                        "계좌 전체 %를 맞추는 화면이 아닙니다."
                    ),
                    do_now=(
                        "매도 줄=25/50/100 · 매수 줄≤33 · HTS에서 회차 금액만 옮기세요."
                    ),
                    ignore="평단 필수 · target 자동 기입 · 포트 캡과 혼동",
                ),
                unsafe_allow_html=True,
            )
            proj = project_portfolio_after_today(
                rows,
                pairs=pairs,
                proposal=list(getattr(ctx, "portfolio_rows", None) or []),
            )
            st.markdown(port_weight_plan_html(proj), unsafe_allow_html=True)
            actionable = board_items(pairs)
            if actionable:
                st.markdown(
                    weight_action_board_html(actionable),
                    unsafe_allow_html=True,
                )
    except Exception:  # noqa: BLE001 — never blank the holdings book
        st.caption("회차 슬라이드를 건너뜀 · 집합 대조로 Review")


def _render_stance_decision(ctx: DashboardContext) -> None:
    """Momentum vs contrarian Soft — same axes as economy compass."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    try:
        from alpha_system.ui.services.stance_decision_board import (
            build_stance_decision_board,
            stance_decision_html,
        )

        board = build_stance_decision_board(Path(ctx.root))
        st.markdown(stance_decision_html(board), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "stance_caption",
                default=(
                    "읽는 법: 위 행 ‘줄임/늘림’만 보면 됨 · "
                    "종목 배지(환금·트레일)가 더 강함 · target 불변"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        st.caption("정발상·역발상 Soft를 건너뜀")


def _render_l3_history_review(ctx: DashboardContext) -> None:
    """L3 crash history + Fear Soft A/B — button-run, never writes target."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    with st.expander(
        copy_get(
            "portfolio",
            "l3_history_expand",
            default="급락 이력 다시 보기 · 버튼 필요",
        ),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose="과거 급락·재진입 패턴 참고용입니다. 오늘 매매 순서를 바꾸지 않습니다.",
                do_now="궁금할 때만「다시 계산」· 전량 강제·자동주문 없음.",
                ignore="결과로 target 기입 · Core 점수 변경",
            ),
            unsafe_allow_html=True,
        )
        market = str(getattr(ctx, "screen_market", None) or "KOSPI").upper()
        run = st.button(
            copy_get(
                "portfolio",
                "l3_history_run",
                default="L3 이력 다시 계산",
            ),
            key=f"l3_hist_run_{market}",
        )
        cache_key = f"l3_hist_report_{market}"
        if run:
            try:
                from alpha_system.shadow.l3_crash_backtest import (
                    run_l3_crash_backtest,
                )
                from alpha_system.shadow.fear_soft_rebal_backtest import (
                    run_fear_soft_rebal_backtest,
                )

                report = run_l3_crash_backtest(
                    Path(ctx.root),
                    market=market,
                    include_target=True,
                )
                fg = run_fear_soft_rebal_backtest(Path(ctx.root))
                st.session_state[cache_key] = (report, fg)
            except Exception:  # noqa: BLE001
                st.caption("L3 이력 Review를 건너뜀")
                return
        packed = st.session_state.get(cache_key)
        if not packed:
            st.caption(
                copy_get(
                    "portfolio",
                    "l3_history_idle",
                    default="버튼을 누르면 보유(+target) 종목으로 이력을 돌립니다.",
                )
            )
            return
        report, fg = packed
        try:
            from alpha_system.shadow.l3_crash_backtest import report_card_html
            from alpha_system.shadow.fear_soft_rebal_backtest import (
                fear_soft_card_html,
            )

            st.markdown(report_card_html(report), unsafe_allow_html=True)
            st.markdown(fear_soft_card_html(fg), unsafe_allow_html=True)
        except Exception:  # noqa: BLE001
            st.caption("L3 이력 카드 렌더 실패")


def _render_shadow_profit_card(ctx: DashboardContext) -> None:
    """Mid shadow P&L card — Review-only, never writes target."""
    try:
        from alpha_system.shadow.mid_ledger import ledger_path, load_ledger
        from alpha_system.shadow.report import shadow_card_html, shadow_report_dict
        from alpha_system.shadow.run import run_shadow_day
    except Exception:  # noqa: BLE001 — optional module
        return

    market = getattr(ctx, "screen_market", None)
    root = Path(ctx.root)
    # Best-effort: append today's step if prices advanced (no-op if already recorded).
    try:
        # 후보(게이트 통과) + 제안 + 보유 → P1 풀 (목표가·가격은 행에 있을 때만 필터).
        cov_extra = []
        for sr in list(getattr(ctx, "scoreboard_rows", None) or []):
            elig = getattr(sr, "eligibility", None)
            if elig is False:
                continue
            cov_extra.append(
                {
                    "ticker": getattr(sr, "ticker", None),
                    "total_score": getattr(sr, "total_score", None),
                    "is_held": bool(getattr(sr, "is_held", False)),
                    "has_target": True,
                    "eligible": True,
                }
            )
        run_shadow_day(
            root,
            market=market,
            proposal_rows=list(getattr(ctx, "portfolio_rows", None) or []) + cov_extra,
            ops_rows=list(getattr(ctx, "ops_portfolio_rows", None) or []),
            persist=True,
        )
    except Exception:  # noqa: BLE001 — shadow must not break holdings UI
        pass
    try:
        rows = load_ledger(ledger_path(root, market))
        rotation_events = None
        try:
            from alpha_system.shadow.rotation_coverage import (
                load_rotation_events,
                rotation_log_path,
            )

            rotation_events = load_rotation_events(rotation_log_path(root, market))
        except Exception:  # noqa: BLE001
            rotation_events = None
        report = shadow_report_dict(rows, rotation_events=rotation_events)
        st.markdown(shadow_card_html(report), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "shadow_profit_caption",
                default=(
                    "연습장 손익 · 실제 매매 지시 아님 · "
                    "곡선·KPI는 사이드바「백테스트」 · target 불변"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        return


def _render_short_vol_budget_banner(ctx: DashboardContext) -> None:
    """Review-only: short sleeve budget card (not per-name weight)."""
    if not is_short(getattr(ctx, "screen_horizon", None)):
        return
    advice = getattr(ctx, "short_vol_budget", None)
    if advice is None:
        return

    level = str(getattr(advice, "level", "") or "") or "missing"
    as_of = str(getattr(advice, "as_of", "") or "")
    action = str(getattr(advice, "action", "") or "")
    scale = float(getattr(advice, "scale", 1.0) or 1.0)
    vix = getattr(advice, "vix", None)
    dd = getattr(advice, "kospi_dd_pct", None)

    level_label = {
        "calm": copy_get("portfolio", "short_vol_level_calm", default="평온"),
        "elevated": copy_get("portfolio", "short_vol_level_elevated", default="고변동"),
        "extreme": copy_get("portfolio", "short_vol_level_extreme", default="극단 변동"),
        "missing": copy_get("portfolio", "short_vol_level_missing", default="데이터없음"),
    }.get(level, level)

    tone = {
        "calm": "calm",
        "elevated": "elevated",
        "extreme": "extreme",
        "missing": "missing",
    }.get(level, "missing")

    scale_pct = int(round(scale * 100))
    if level == "calm":
        scale_line = copy_get(
            "portfolio",
            "short_vol_scale_full",
            default="평소 100%",
        )
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_ok",
            default="위성 예산 유지",
        )
    elif level == "missing":
        scale_line = "—"
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_na",
            default="권고 불가",
        )
    else:
        scale_line = f"{scale_pct}%"
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_cut",
            default="평소 대비 목표",
        )

    if not action:
        if level == "missing":
            action = copy_get(
                "portfolio",
                "short_vol_action_missing",
                default="시장 지표 갱신 후 재확인",
            )
        else:
            action = copy_get(
                "portfolio",
                "short_vol_action_ok",
                default="평소 단기 예산 유지 가능",
            )

    chips: list[str] = []
    if vix is not None:
        try:
            chips.append(f"VIX {float(vix):g}")
        except (TypeError, ValueError):
            pass
    if dd is not None:
        try:
            chips.append(f"코스피 고가대비 {float(dd):+.1f}%")
        except (TypeError, ValueError):
            pass
    if as_of:
        chips.append(f"as_of {as_of}")
    chips_html = (
        "".join(f'<span class="svb-chip">{_esc(c)}</span>' for c in chips)
        if chips
        else f'<span class="svb-chip">{_esc(copy_get("portfolio", "short_vol_chip_empty", default="지표 없음"))}</span>'
    )

    kicker = copy_get(
        "portfolio",
        "short_vol_kicker",
        default="단기 위성 예산",
    )
    do_lab = copy_get("portfolio", "short_vol_row_do", default="할 일")
    why_lab = copy_get("portfolio", "short_vol_row_why", default="근거")
    foot = copy_get(
        "portfolio",
        "short_vol_foot",
        default="종목당 비중·단기채 비율이 아님 · Review-only · 자동매도 없음",
    )

    html_block = (
        f'<div class="svb-card svb-card-{_esc(tone)}">'
        f'<div class="svb-kicker">{_esc(kicker)}</div>'
        f'<div class="svb-head">'
        f'<div class="svb-level">{_esc(level_label)}</div>'
        f'<div class="svb-scale-wrap">'
        f'<div class="svb-scale">{_esc(scale_line)}</div>'
        f'<span class="svb-scale-label">{_esc(scale_sub)}</span>'
        f"</div></div>"
        f'<div class="svb-row"><span class="svb-row-lab">{_esc(do_lab)}</span>'
        f"<div>{_esc(action)}</div></div>"
        f'<div class="svb-row"><span class="svb-row-lab">{_esc(why_lab)}</span>'
        f'<div class="svb-metrics">{chips_html}</div></div>'
        f'<div class="svb-foot">{_esc(foot)}</div>'
        f"</div>"
    )
    st.markdown(html_block, unsafe_allow_html=True)


def _render_monthly_rebal_note(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.monthly_rebal_board import build_monthly_rebal_board

    board = build_monthly_rebal_board(ctx)
    if not board.do_now_count:
        return
    st.caption(
        copy_get(
            "portfolio",
            "rebal_note",
            default="월 리밸 참고 {n}건 — Review-only · target 자동기입 없음.",
            n=board.do_now_count,
        )
    )


def _current_alpha_paste(ctx: DashboardContext) -> str:
    from alpha_system.ui.services.holdings_input import (
        HoldingDraft,
        format_drafts_as_paste,
    )

    drafts: list[HoldingDraft] = []
    path = ctx.data_dir / "positions.csv"
    if path.exists():
        try:
            df = pd.read_csv(path, dtype=str)
            if not df.empty and "asset_group" in df.columns:
                kr = df[df["asset_group"].astype(str) == "kr_alpha"]
                for _, row in kr.iterrows():
                    try:
                        q = float(row.get("quantity") or 0)
                    except (TypeError, ValueError):
                        q = 0.0
                    try:
                        ap = (
                            float(row["avg_price"])
                            if str(row.get("avg_price") or "").strip()
                            else None
                        )
                    except (TypeError, ValueError):
                        ap = None
                    drafts.append(
                        HoldingDraft(
                            ticker=str(row.get("ticker") or "").zfill(6),
                            quantity=q,
                            avg_price=ap,
                            name=str(row.get("name") or ""),
                        )
                    )
        except Exception:
            pass
    if not drafts:
        for r in ctx.ops_portfolio_rows or []:
            drafts.append(
                HoldingDraft(
                    ticker=str(r.ticker).zfill(6),
                    quantity=0.0,
                    avg_price=r.avg_price,
                    name=str(r.name or ""),
                )
            )
    return format_drafts_as_paste(drafts)


def _saved_kr_alpha_rows(ctx: DashboardContext) -> list[dict[str, object]]:
    """Read kr_alpha rows from positions.csv (includes qty=0 placeholders)."""
    path = ctx.data_dir / "positions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        return []
    if df.empty or "ticker" not in df.columns:
        return []
    if "asset_group" in df.columns:
        df = df[df["asset_group"].astype(str) == "kr_alpha"]
    out: list[dict[str, object]] = []
    for _, row in df.iterrows():
        raw = str(row.get("ticker") or "").strip()
        if not raw:
            continue
        tk = raw.zfill(6) if raw.isdigit() else raw
        try:
            qty = float(row.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        out.append({"ticker": tk, "name": str(row.get("name") or tk), "quantity": qty})
    return out


def _persist_watch_holdings(ctx: DashboardContext, tickers: list[str]) -> None:
    from alpha_system.ui.services.holdings_input import (
        drafts_from_tickers,
        upsert_kr_alpha_positions,
    )

    drafts = drafts_from_tickers(tickers, root=ctx.root)
    path = ctx.data_dir / "positions.csv"
    upsert_kr_alpha_positions(
        path,
        drafts,
        root=ctx.root,
        replace_alpha=True,
        keep_zero_qty=True,
        keep_existing_meta=True,
    )
    st.session_state["holdings_input_open"] = True
    st.session_state["holdings_paste_pending"] = _current_alpha_paste(ctx)


def _extra_by_ticker(ctx: DashboardContext) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in list(ctx.portfolio_rows or []) + list(
        getattr(ctx, "proposal_blocked_rows", None) or []
    ) + list(ctx.ops_portfolio_rows or []):
        tk = str(row.ticker).zfill(6)
        extra = dict(row.extra or {})
        if getattr(row, "target_price", None) is not None:
            extra.setdefault("target_price", row.target_price)
        out[tk] = extra
    return out


def _style_watch_df(frame: pd.DataFrame):
    from alpha_system.ui.theme_prefs import normalize_theme, watch_row_styles

    theme = normalize_theme(st.session_state.get("saa_ui_theme") or "dark")
    tones = watch_row_styles(theme)

    def _hl(row: pd.Series) -> list[str]:
        css = tones.get(str(row.get("구분") or ""), "")
        return [css] * len(row)

    return frame.style.apply(_hl, axis=1)


def _watch_hakedaka_by_ticker(
    ctx: DashboardContext, tickers: list[str]
) -> dict[str, str]:
    """Gate summary for the observation table. Not score_sr / not a 0–100 score."""
    from alpha_system.sizing.hakedaka_screen import (
        evaluate_hakedaka,
        hits_label_short,
        load_hakedaka_inputs,
    )

    if is_short(getattr(ctx, "screen_horizon", None)):
        return {str(t).zfill(6) if str(t).isdigit() else str(t): "단기 미적용" for t in tickers}
    if not bool(getattr(ctx.cfg.sizing, "hakedaka_gate_enabled", True)):
        return {str(t).zfill(6) if str(t).isdigit() else str(t): "게이트 off" for t in tickers}

    book = _source_dir(ctx)
    inputs = load_hakedaka_inputs(ctx.root, data_dir=book)
    min_hits = int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2)
    out: dict[str, str] = {}
    for raw in tickers:
        tk = str(raw).zfill(6) if str(raw).isdigit() else str(raw)
        out[tk] = hits_label_short(evaluate_hakedaka(tk, inputs, min_hits=min_hits))
    return out


def _watch_eval_enrichment(
    ctx: DashboardContext, tickers: list[str]
) -> dict[str, dict[str, str]]:
    """판정·심층·공시 from disk caches only (no network)."""
    from alpha_system.review.screen_deep_verify import load_screen_verify
    from alpha_system.sizing.qual_overlay import load_qual_overlay, overlay_path
    from alpha_system.ui.services.cecs_opendart_pack import load_opendart_watch
    from alpha_system.ui.services.opendart_evidence_board import (
        build_watch_eval_map,
        parse_evidence_board,
    )

    data_dir = Path(_source_dir(ctx))
    try:
        sv_board = load_screen_verify(data_dir)
        sv_rows = list(sv_board.rows)
    except Exception:  # noqa: BLE001
        sv_rows = []
    flags: list = []
    evidence: list = []
    try:
        snap = load_opendart_watch(ctx.root, data_dir=data_dir)
        if snap is not None:
            flags = list(snap.flag_models())
            evidence = parse_evidence_board(getattr(snap, "evidence", None) or [])
    except Exception:  # noqa: BLE001
        pass
    gated: set[str] = set()
    try:
        gated = set(load_qual_overlay(overlay_path(data_dir)).gated_tickers())
    except Exception:  # noqa: BLE001
        gated = set()
    return build_watch_eval_map(
        tickers,
        screen_verify_rows=sv_rows,
        board=evidence,
        flags=flags,
        gated=gated,
    )


def _proposal_weight_by_ticker(ctx: DashboardContext) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in list(ctx.portfolio_rows or []):
        tk = str(getattr(r, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            try:
                out[tk] = float(r.weight_pct)
            except (TypeError, ValueError):
                continue
    return out


def _render_watch_pool(
    ctx: DashboardContext,
    preview_cutoff: float | None,
    preview_n: int,
) -> None:
    watch_key, watch_sig, watch_last = _watch_session_keys(ctx)
    saved = _saved_kr_alpha_rows(ctx)
    saved_tickers = {str(r["ticker"]) for r in saved}
    proposal_tickers = {str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])}
    blocked_tickers = {
        str(r.ticker).zfill(6)
        for r in (getattr(ctx, "proposal_blocked_rows", None) or [])
    }
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers=proposal_tickers,
        held_tickers=saved_tickers,
        proposal_band_max=int(preview_n),
        max_rows=watch_max(
            getattr(ctx, "screen_market", None),
            getattr(ctx, "screen_horizon", None),
        ),
    )
    metrics = load_watch_metrics(ctx.root, data_dir=_source_dir(ctx))
    hk_map = _watch_hakedaka_by_ticker(ctx, [r.ticker for r in board.rows])
    table_rows = build_watch_table_rows(
        board,
        metrics=metrics,
        extra_by_ticker=_extra_by_ticker(ctx),
        sector_labels=load_sector_labels(ctx.root),
        cutoff=preview_cutoff,
        target_n=int(preview_n),
        blocked_tickers=blocked_tickers,
        hakedaka_by_ticker=hk_map,
    )
    watch_tickers = [r.ticker for r in board.rows]
    regime_board = build_sector_regime_board(
        ctx.scoreboard_rows or [],
        root=ctx.root,
        data_dir=_source_dir(ctx),
        held_tickers=list(saved_tickers),
        proposal_tickers=list(proposal_tickers),
        watch_tickers=watch_tickers,
        tickers_for_chips=watch_tickers,
        include_complements=False,
    )

    short_watch = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        legend = (
            '<div class="pf-watch-legend">'
            '<span><span class="pf-swatch pf-swatch-proposal"></span>'
            f"{copy_get('portfolio', 'watch_legend_proposal', default='최종 제안')}</span>"
            '<span><span class="pf-swatch pf-swatch-eligible"></span>'
            f"{copy_get('portfolio', 'watch_legend_eligible', default='컷 통과')}</span>"
            '<span><span class="pf-swatch pf-swatch-blocked"></span>'
            f"{copy_get('portfolio', 'watch_legend_blocked', default='편입 제외')}</span>"
            '<span><span class="pf-swatch pf-swatch-watch"></span>'
            f"{copy_get('portfolio', 'watch_legend_watch', default='관찰')}</span>"
            "</div>"
        )
        regime_chips: list[tuple[str, str]] = [
            ("평가 통합 표", "ok"),
            ("「보유」→ ④", "ok"),
            (
                copy_get(
                    "portfolio",
                    "regime_fit_chip",
                    default="국면적합 Review",
                ),
                "ok",
            ),
        ]
        if regime_board.stage is not None:
            stage_txt = (
                f"{regime_board.stage}단계"
                + (f" · {regime_board.stage_label}" if regime_board.stage_label else "")
            )
            regime_chips.append((stage_txt, "ok"))
        _render_section_head(
            copy_get("portfolio", "sec_watch", default="② 후보"),
            summary=copy_get(
                "portfolio",
                "watch_intro_short" if short_watch else "watch_intro",
                default=(
                    "한 표=점수·판정·심층·공시·하케다카 · 행 색=③ 관계 · 「보유」=④."
                    if short_watch
                    else (
                        "한 표에 점수·판정·심층·공시·하케다카·가격을 모음 · "
                        "행 색=최종 제안/컷 통과/편입 제외 · 「보유」체크=④ 실보유."
                    )
                ),
            ),
            chips=regime_chips,
            extra_html=legend,
            tier="primary",
        )
        if board.warnings:
            for w in board.warnings:
                st.caption(w)
        if board.held_outside:
            outside = " · ".join(
                f"{r.name} ({r.ticker}) {r.rank}위" for r in board.held_outside
            )
            st.warning(
                f"관찰 {watch_max(getattr(ctx, 'screen_market', None), getattr(ctx, 'screen_horizon', None))} 밖 — "
                f"잔류하지 않음: {outside}. "
                "표에서 체크를 바꾸면 알파에서 빠집니다."
            )
        if not table_rows:
            st.info("스크린된 관찰 종목이 없습니다. 점수판·컷오프를 확인하세요.")
        else:
            records = []
            short = is_short(getattr(ctx, "screen_horizon", None))
            absorb_map = {}
            if short:
                from alpha_system.ui.services.short_absorb_signal import (
                    absorb_label_for_ticker,
                    build_absorb_map,
                )

                absorb_map = build_absorb_map(
                    ctx.root, getattr(ctx, "screen_market", None)
                )
            eval_map = _watch_eval_enrichment(
                ctx, [r.ticker for r in table_rows]
            )
            weight_map = _proposal_weight_by_ticker(ctx)
            for r in table_rows:
                tk = str(r.ticker).zfill(6) if str(r.ticker).isdigit() else str(r.ticker)
                ev = eval_map.get(tk) or {}
                w = weight_map.get(tk)
                fit_lbl = fit_label_for_ticker(regime_board, r.ticker)
                fit_why = fit_why_for_ticker(regime_board, r.ticker)
                rec = {
                    "보유": r.ticker in saved_tickers,
                    "순위": r.rank,
                    "구분": watch_tone_label(r.tone),
                    "국면적합": fit_lbl,
                    "종목": r.name,
                    "차트": naver_fchart_url(r.ticker),
                    "코드": r.ticker,
                    "점수": r.total_score,
                    "SR": r.score_sr,
                    "판정": ev.get("판정") or "—",
                    "심층": ev.get("심층") or "—",
                    "공시": ev.get("공시") or "—",
                    "하케다카": r.hakedaka or "—",
                    "제안%": round(w, 1) if w is not None else None,
                    "배당%": r.dividend_yield,
                    "섹터": r.sector or "—",
                    "국면why": fit_why or "—",
                    "PER": r.per,
                    "PBR": r.pbr,
                    "ROE": r.roe,
                    "현재가": r.current_price,
                    "목표가": r.target_price,
                }
                if short:
                    rec["흡수"] = absorb_label_for_ticker(absorb_map, r.ticker)
                records.append(rec)
            frame = pd.DataFrame.from_records(records)
            saved_in_30 = tuple(
                sorted(r.ticker for r in table_rows if r.ticker in saved_tickers)
            )
            sig = tuple(r.ticker for r in table_rows)
            if st.session_state.get(watch_sig) != sig:
                st.session_state.pop(watch_key, None)
                st.session_state[watch_sig] = sig
                st.session_state[watch_last] = saved_in_30

            # 「보유」체크 + 구분 행 색 · 좁은 창은 가로 스크롤(깨짐 방지).
            locked_cols = [c for c in frame.columns if c != "보유"]
            core_cols = [
                "보유",
                "순위",
                "구분",
                "국면적합",
                "종목",
                "차트",
                "점수",
                "SR",
                "판정",
                "심층",
                "공시",
                "하케다카",
                "제안%",
                "현재가",
                "목표가",
            ]
            extra_cols = [
                c
                for c in (
                    "코드",
                    "배당%",
                    "섹터",
                    "국면why",
                    "PER",
                    "PBR",
                    "ROE",
                    "흡수",
                )
                if c in frame.columns
            ]
            compact = st.toggle(
                copy_get(
                    "portfolio",
                    "watch_compact_cols",
                    default="핵심 열만 (좁은 창)",
                ),
                value=False,
                key=f"{watch_key}_compact",
                help="켜면 차트·코드·PER 등을 숨기고 평가 열을 남깁니다. 끄면 가로 스크롤.",
            )
            show_cols = [c for c in core_cols if c in frame.columns]
            if not compact:
                show_cols = show_cols + [c for c in extra_cols if c not in show_cols]
            # Keep any unexpected columns at the end when not compact.
            if not compact:
                show_cols = show_cols + [
                    c for c in frame.columns if c not in show_cols
                ]
            st.markdown('<div class="pf-watch-scroll">', unsafe_allow_html=True)
            edited = st.data_editor(
                _style_watch_df(frame),
                hide_index=True,
                width="stretch",
                height=38 + 33 * len(frame),
                row_height=32,
                disabled=locked_cols,
                column_order=show_cols,
                key=watch_key,
                placeholder="—",
                column_config={
                    "보유": st.column_config.CheckboxColumn(
                        "보유",
                        help="체크 = ④ 실보유 등록 · 바로 저장 · 자동매매 없음",
                        default=False,
                        width="small",
                    ),
                    "구분": st.column_config.TextColumn(
                        "구분",
                        help="행 색과 동일 · 최종 제안=녹 · 컷 통과=주황 · 편입 제외=적 · 관찰=기본",
                        width="small",
                    ),
                    "국면적합": st.column_config.TextColumn(
                        "국면적합",
                        help=(
                            copy_get(
                                "portfolio",
                                "regime_fit_help",
                                default=(
                                    "경제 나침반 국면×업종 Review · 유리/중립/불리/보류 · "
                                    "QVM 점수·순위·target 불변"
                                ),
                            )
                        ),
                        width="small",
                    ),
                    "국면why": st.column_config.TextColumn(
                        "국면why",
                        help="국면적합 한 줄 근거 · Review-only",
                        width="medium",
                    ),
                    "순위": st.column_config.NumberColumn(
                        "순위", format="%d", width="small"
                    ),
                    "종목": st.column_config.TextColumn("종목", width="medium"),
                    "차트": st.column_config.LinkColumn(
                        "차트",
                        help="네이버 일봉 차트",
                        display_text="차트",
                        width="small",
                    ),
                    "코드": st.column_config.TextColumn("코드", width="small"),
                    "점수": st.column_config.NumberColumn(
                        "점수", format="%.2f", width="small"
                    ),
                    "SR": st.column_config.NumberColumn(
                        "SR",
                        format="%.1f",
                        help="환원 score_sr (배당·성향·자사주·연속성) · 합계 25%",
                        width="small",
                    ),
                    "판정": st.column_config.TextColumn(
                        "판정",
                        help="스크린 심층 Review · 통과/보류/제외검토 · 점수·target 불변",
                        width="small",
                    ),
                    "심층": st.column_config.TextColumn(
                        "심층",
                        help="자동 심층 사유 · 사람만 편입·주문",
                        width="medium",
                    ),
                    "공시": st.column_config.TextColumn(
                        "공시",
                        help="OpenDART 가치실현·게이트 요약 · 캐시 기준",
                        width="medium",
                    ),
                    "제안%": st.column_config.NumberColumn(
                        "제안%",
                        format="%.1f",
                        help="③ 최종 제안 비중(%) · 없으면 빈칸",
                        width="small",
                    ),
                    "배당%": st.column_config.NumberColumn(
                        "배당%",
                        format="%.2f",
                        help="배당수익률(%) · 후보 30 안에서만 표시",
                        width="small",
                    ),
                    "하케다카": st.column_config.TextColumn(
                        "하케다카",
                        help=(
                            "순차 게이트 · 절대 4축(순현금·자사주·최대주주·순환출자). "
                            "예: 2/4 통과 · 미측정 1 = 충족 2, 미측정 1, 나머지 불충족. "
                            "×는 ‘측정됐는데 아님’ · 미측정과 다름. "
                            "합계·환원(score_sr)과 별개 · 단기 북은 미적용."
                        ),
                        width="small",
                    ),
                    "섹터": st.column_config.TextColumn("섹터", width="small"),
                    "흡수": st.column_config.TextColumn(
                        "흡수",
                        help=(
                            "단기 Review · 거래대금≥20일평균 3배 and 1M 수익률≤+3% "
                            "(급락 −20% 미만 제외). 매집 단정 아님 · 자동매수 없음."
                        ),
                        width="small",
                    ),
                    "PER": st.column_config.NumberColumn(
                        "PER", format="%.2f", width="small"
                    ),
                    "PBR": st.column_config.NumberColumn(
                        "PBR", format="%.2f", width="small"
                    ),
                    "ROE": st.column_config.NumberColumn(
                        "ROE", format="%.1f", width="small"
                    ),
                    "현재가": st.column_config.NumberColumn(
                        "현재가", format="%.0f", width="small"
                    ),
                    "목표가": st.column_config.NumberColumn(
                        "목표가", format="%.0f", width="small"
                    ),
                },
            )
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption(
                copy_get(
                    "portfolio",
                    "watch_hakedaka_caption",
                    default=(
                        "하케다카 = 게이트 · 절대 /4 · SR·배당% = 환원 참고(점수 혼합 아님) · "
                        "미달이면 중기 최종 제안에서 제외될 수 있음 · "
                        "순환출자는 True만 측정(대부분 미측정이 정상)"
                    ),
                )
            )
            st.caption(
                copy_get(
                    "portfolio",
                    "regime_fit_caption",
                    default=(
                        "국면적합 = 나침반 stage×업종 Review · 점수 가산 없음 · "
                        "target 자동기입 없음 · 맵은 alpha_system/config/sector_regime_fit.yaml"
                    ),
                )
            )
            from alpha_system.sizing.hakedaka_screen import (
                coverage_for_tickers,
                load_hakedaka_inputs,
            )

            cov = coverage_for_tickers(
                [r.ticker for r in board.rows],
                load_hakedaka_inputs(ctx.root, data_dir=_source_dir(ctx)),
                min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
            )
            st.caption(cov.caption())
            if cov.n and cov.owner == 0:
                st.caption(
                    copy_get(
                        "portfolio",
                        "watch_hakedaka_owner_gap",
                        default=(
                            "최대주주 0% — OpenDART「다시 탐색」으로 관찰 풀만 보강 "
                            "(corp 코드 캐시·API). 전 유니버스가 아님."
                        ),
                    )
                )
            hold_flags = _watch_hold_flags(edited, n=len(table_rows))
            sel_tickers = [
                table_rows[i].ticker
                for i, on in enumerate(hold_flags)
                if on
            ]
            current = tuple(sorted(sel_tickers))
            prev = st.session_state.get(watch_last)
            if prev is None:
                st.session_state[watch_last] = saved_in_30
            elif current != prev:
                _persist_watch_holdings(ctx, list(current))
                st.session_state[watch_last] = current
                st.session_state.pop(watch_key, None)
                st.rerun()

        _render_candidate_ai_export(
            ctx,
            table_rows,
            preview_cutoff=preview_cutoff,
            preview_n=int(preview_n),
        )
        _render_holdings_paste(ctx)


def _render_candidate_ai_export(
    ctx: DashboardContext,
    table_rows,
    *,
    preview_cutoff: float | None,
    preview_n: int,
) -> None:
    pack = build_candidate_ai_export(
        market=getattr(ctx, "screen_market", "KOSPI"),
        as_of=ctx.as_of,
        cutoff=preview_cutoff,
        quality_min=getattr(ctx.cfg.scoring, "quality_min_score", None),
        target_n=int(preview_n),
        table_rows=table_rows,
        scoreboard_rows=ctx.scoreboard_rows or [],
        root=ctx.root,
        data_dir=_source_dir(ctx),
        hakedaka_min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
    )
    mkt = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    with st.expander(
        copy_get("portfolio", "watch_ai_export_expand", default="다른 AI에 붙여넣기"),
        expanded=False,
    ):
        st.caption(
            copy_get(
                "portfolio",
                "watch_ai_export",
                default=(
                    "관찰 풀·점수·현재가·목표가를 Markdown/JSON으로 내려 "
                    "다른 AI에 붙입니다. target 파일·자동매매 없음."
                ),
            )
        )
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Markdown 저장",
                data=pack.markdown.encode("utf-8"),
                file_name=f"{pack.file_stem}.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
                key=f"pf_ai_export_md_{mkt}",
            )
        with c2:
            st.download_button(
                "JSON 저장",
                data=pack.json_text.encode("utf-8"),
                file_name=f"{pack.file_stem}.json",
                mime="application/json; charset=utf-8",
                use_container_width=True,
                key=f"pf_ai_export_json_{mkt}",
            )
        st.code(pack.markdown, language="markdown")


def _render_holdings_paste(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.holdings_input import (
        parse_holdings_paste,
        upsert_kr_alpha_positions,
    )

    pending = st.session_state.pop("holdings_paste_pending", None)
    if pending is not None:
        st.session_state["holdings_paste_text"] = pending
    elif "holdings_paste_text" not in st.session_state:
        st.session_state["holdings_paste_text"] = _current_alpha_paste(ctx)

    with st.expander(
        copy_get(
            "portfolio",
            "holdings_paste_title",
            default="보유 티커 붙이기 · 집합 대조용",
        ),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "지금 들고 있는 종목코드를 등록해 "
                    "위「둘 다·제안만·보유만」대조에 쓰입니다."
                ),
                do_now="한 줄에 6자리 코드만 넣어도 됨 · 저장 후 집합 다시 확인.",
                ignore="평단·수량 필수 · 여기 붙인다고 자동매수",
            ),
            unsafe_allow_html=True,
        )
        text = st.text_area(
            "보유 목록",
            key="holdings_paste_text",
            height=140,
            placeholder="005930\n000660\n035420\n# 또는 005930 100 45000",
            label_visibility="collapsed",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "티커 저장",
                type="primary",
                key="holdings_save",
                use_container_width=True,
            ):
                parsed = parse_holdings_paste(text)
                if parsed.errors and not parsed.drafts:
                    for e in parsed.errors:
                        st.error(e)
                else:
                    for e in parsed.errors:
                        st.warning(e)
                    path = ctx.data_dir / "positions.csv"
                    membership_only = any(d.quantity <= 0 for d in parsed.drafts)
                    result = upsert_kr_alpha_positions(
                        path,
                        parsed.drafts,
                        root=ctx.root,
                        replace_alpha=True,
                        keep_zero_qty=membership_only,
                    )
                    saved_tks = [d.ticker for d in parsed.drafts]
                    _reset_watch_picker(ctx, saved_tks)
                    st.session_state["holdings_input_open"] = True
                    st.session_state["holdings_paste_pending"] = format_drafts_helper(
                        parsed.drafts
                    )
                    st.success(
                        f"알파 {result['alpha_count']}종 저장 · "
                        f"기타 {result['kept_other']}행 유지"
                    )
                    st.rerun()
        with c2:
            if st.button(
                "알파 비우기",
                key="holdings_clear_alpha",
                use_container_width=True,
            ):
                path = ctx.data_dir / "positions.csv"
                upsert_kr_alpha_positions(
                    path, [], root=ctx.root, replace_alpha=True
                )
                _reset_watch_picker(ctx, [])
                st.session_state["holdings_paste_pending"] = ""
                st.session_state["holdings_input_open"] = True
                st.rerun()
        preview = parse_holdings_paste(
            st.session_state.get("holdings_paste_text") or ""
        )
        if preview.drafts:
            st.caption(
                f"인식 {len(preview.drafts)}종"
                + (f" · 경고 {len(preview.errors)}" if preview.errors else "")
            )


def format_drafts_helper(drafts) -> str:
    from alpha_system.ui.services.holdings_input import format_drafts_as_paste

    return format_drafts_as_paste(drafts)


def _render_sector_exposure(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.sector_exposure import assess_sector_weight_caps

    rows = ctx.portfolio_rows or []
    if not rows:
        return
    exposures = assess_sector_weight_caps(rows, data_dir=_source_dir(ctx))
    overs = [e for e in exposures if e.over]
    if overs:
        for e in overs:
            tickers = ", ".join(e.tickers)
            st.warning(
                copy_get(
                    "portfolio",
                    "sector_cap_over",
                    default=(
                        f"섹터 합산 {e.bucket} {e.weight_pct}% > 한도 {e.limit_pct}% "
                        f"({e.name_count}종: {tickers}) — 비중·편입 재검토"
                    ),
                    bucket=e.bucket,
                    weight=f"{e.weight_pct:.1f}",
                    limit=f"{e.limit_pct:.0f}",
                    tickers=tickers,
                    n=str(e.name_count),
                )
            )
    else:
        return


def _render_revalidate_flags(ctx: DashboardContext) -> None:
    flagged = [
        r
        for r in (ctx.portfolio_rows or [])
        if (r.extra or {}).get("revalidate_required")
    ]
    if not flagged:
        return
    lines = []
    for r in flagged:
        reason = (r.extra or {}).get("revalidate_reason") or "목표가 재검증 필요"
        as_of = (r.extra or {}).get("approved_as_of") or "—"
        lines.append(f"`{r.ticker}` {r.name}: {reason} (승인 {as_of})")
    st.warning("목표가 재검증\n\n" + "\n\n".join(lines))


def _render_cutoff_bar(ctx: DashboardContext) -> tuple[float | None, int]:
    """Compact cutoff + book-size controls. YAML unchanged until confirm.

    Returns (preview_cutoff, preview_target_n) for table coloring.
    """
    scored = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "total_score": row.total_score,
            "score_q": row.score_q,
        }
        for row in ctx.scoreboard_rows
        if row.total_score is not None
    ]
    ladder = build_relative_cutoff_ladder(scored, min_rank=1)
    current_n = int(ctx.cfg.sizing.target_names)
    current_cutoff = ctx.cfg.scoring.score_cutoff
    rec = recommended_absolute_cutoff_option(ladder, scored)

    yaml_n = current_n
    n_min, n_max, n_default = target_names_band(
        getattr(ctx, "screen_market", None),
        getattr(ctx, "screen_horizon", None),
    )
    if yaml_n < n_min or yaml_n > n_max:
        yaml_n = n_default

    mkt = _book_keys(ctx)
    cutoff_key = f"portfolio_cutoff_natural_break_{mkt}"
    count_key = f"portfolio_target_names_band_{mkt}"

    with st.container(border=True):
        yaml_label = (
            f"{current_cutoff:.2f}" if current_cutoff is not None else "미확정"
        )
        _render_section_head(
            copy_get("portfolio", "sec_cutoff", default="① 선정 규칙"),
            summary=copy_get(
                "portfolio",
                "cutoff_caption",
                default="합격선·편입 수를 고른 뒤 아래에서 확정. 확정 전 YAML·제안 북은 그대로.",
            ),
            chips=[
                (f"저장 컷 {yaml_label}", "muted"),
                (f"편입 {current_n}종", "muted"),
            ],
            tier="input",
        )
        if not ladder or rec is None:
            _render_status_card(
                "컷오프를 계산할 유효 스코어가 없습니다. 확인 → ① 정량을 갱신하세요.",
                tone="warn",
            )
            return current_cutoff, yaml_n

        natural = [option for option in ladder if option.is_natural_break]
        if rec not in natural:
            natural = [rec, *natural]
        by_rank = {option.rank_n: option for option in natural}
        break_ranks = [option.rank_n for option in natural]

        def _session_rank(key: str, allowed) -> int | None:
            raw = st.session_state.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None
            if value in allowed:
                return value
            return None

        if _session_rank(cutoff_key, by_rank) is None:
            matched = None
            if current_cutoff is not None:
                matched = next(
                    (
                        option
                        for option in natural
                        if abs(float(option.cutoff) - float(current_cutoff)) < 1e-6
                    ),
                    None,
                )
            st.session_state[cutoff_key] = (
                matched.rank_n if matched is not None else rec.rank_n
            )
        if _session_rank(count_key, set(range(n_min, n_max + 1))) is None:
            st.session_state[count_key] = yaml_n

        _render_control_card(
            "점수 컷오프",
            hint="합격선 · 아래 선택 · 표 색만 미리보기",
        )
        picked = st.radio(
            "점수 컷오프",
            options=break_ranks,
            format_func=lambda rank: (
                f"{by_rank[rank].cutoff:.2f} · 적격 {by_rank[rank].eligible_count}종"
                + (" · 권고" if rec is not None and rank == rec.rank_n else "")
            ),
            horizontal=True,
            key=cutoff_key,
            label_visibility="collapsed",
        )
        cutoff_opt = by_rank[int(picked)]
        _render_control_card(
            "제안 편입 수",
            hint="컷 통과 종목 중 제안에 담을 최대 수",
        )
        target_n = st.radio(
            "제안 편입 수",
            options=list(range(n_min, n_max + 1)),
            horizontal=True,
            key=count_key,
            label_visibility="collapsed",
        )

        preview_scores = [
            NameScore(
                ticker=row.ticker,
                name=row.name,
                factors={},
                total_score=float(row.total_score),
                eligibility=True,
                weight_input=float(row.total_score),
                eligibility_reason="preview",
                sector=str(getattr(row, "sector", "") or ""),
            )
            for row in ctx.scoreboard_rows
            if row.total_score is not None
            and float(row.total_score) >= float(cutoff_opt.cutoff)
        ]
        preview_alloc = allocate_tranche(
            ctx.cfg.model_copy(
                update={
                    "scoring": ctx.cfg.scoring.model_copy(
                        update={"score_cutoff": cutoff_opt.cutoff}
                    ),
                    "sizing": ctx.cfg.sizing.model_copy(
                        update={"target_names": int(target_n)}
                    ),
                }
            ),
            tranche_id=TrancheId.T1,
            scores=preview_scores,
            existing_weights={},
            tranche_budget=1.0,
            overlay=load_qual_overlay(overlay_path(_source_dir(ctx))),
            exclude_tickers=collect_above_justified_target_tickers_from_root(
                [s.ticker for s in preview_scores],
                ctx.root,
            ),
        )
        selected_n = sum(
            1 for a in preview_alloc.allocated if a.incremental_weight > 0
        )
        _render_status_card(
            f"미리보기 컷 {cutoff_opt.cutoff:.2f} · 적격 {cutoff_opt.eligible_count}종 · "
            f"편입 {int(target_n)}종 · 제안 예상 {selected_n}종 "
            f"(저장 {yaml_label} / {current_n}종) · 확정 전 YAML·제안 북 불변",
            tone="ok",
        )

        changed = (
            current_n != int(target_n)
            or current_cutoff is None
            or abs(float(current_cutoff) - cutoff_opt.cutoff) > 1e-9
        )
        with st.expander("이 규칙으로 확정", expanded=current_cutoff is None):
            boundary = (
                f"경계 {cutoff_opt.boundary_ticker} {cutoff_opt.boundary_name}"
                + (
                    f" · 바로 아래 {cutoff_opt.next_ticker} "
                    f"{cutoff_opt.next_name} · 갭 {cutoff_opt.margin_below:.2f}"
                    if cutoff_opt.next_ticker is not None
                    and cutoff_opt.margin_below is not None
                    else ""
                )
            )
            _render_status_card(boundary, tone="muted")
            if not changed:
                st.success("현재 설정과 동일합니다.")
            else:
                confirm_1 = st.checkbox(
                    "절대 컷오프와 경계 종목을 확인했습니다",
                    key=f"portfolio_abs_cutoff_confirm_1_{mkt}",
                )
                confirm_2 = st.checkbox(
                    "확정 시 점수 컷오프·편입 종목 수가 바뀌고 제안 북이 재계산됨을 이해했습니다 "
                    "(목표 포트 파일은 변경되지 않음)",
                    key=f"portfolio_abs_cutoff_confirm_2_{mkt}",
                )
                if st.button(
                    "절대 컷오프·편입 수 최종 확정",
                    type="primary",
                    disabled=not (confirm_1 and confirm_2),
                    use_container_width=True,
                    key=f"portfolio_abs_cutoff_save_{mkt}",
                ):
                    try:
                        if is_short(getattr(ctx, "screen_horizon", None)):
                            backup = save_short_policy(
                                ctx.root,
                                getattr(ctx, "screen_market", None),
                                cutoff=cutoff_opt.cutoff,
                                target_names=int(target_n),
                            )
                        elif is_kosdaq(getattr(ctx, "screen_market", None)):
                            backup = save_kosdaq_policy(
                                ctx.root,
                                cutoff=cutoff_opt.cutoff,
                                target_names=int(target_n),
                            )
                        else:
                            backup = confirm_score_cutoff(
                                config_path=(
                                    ctx.root / "alpha_system" / "config" / "alpha_system.yaml"
                                ),
                                cecs_path=(
                                    ctx.root / "data" / "cecs_manual_scoring_template.csv"
                                ),
                                cutoff=cutoff_opt.cutoff,
                                confirm_understood=confirm_1,
                                confirm_final=confirm_2,
                                as_of=ctx.as_of or _date.today(),
                                journal_path=ctx.root / "data" / "alpha_system_journal.jsonl",
                                eligible_count=cutoff_opt.eligible_count,
                                rank_n=cutoff_opt.rank_n,
                                method="absolute_cutoff_then_count",
                                target_names=int(target_n),
                            )
                    except Exception as exc:
                        st.error(str(exc))
                    else:
                        proposal_tickers = [
                            str(a.ticker).zfill(6)
                            for a in preview_alloc.allocated
                            if float(a.incremental_weight) > 0
                        ]
                        if proposal_tickers:
                            try:
                                from alpha_system.ui.services.cecs_opendart_pack import (
                                    refresh_opendart_proposal_watch,
                                )

                                with st.spinner("확정된 제안 종목 OpenDART 탐색"):
                                    refresh_opendart_proposal_watch(
                                        ctx.root,
                                        proposal_tickers,
                                        as_of=ctx.as_of if isinstance(ctx.as_of, _date) else _date.today(),
                                        journal_path=ctx.root / "data" / "alpha_system_journal.jsonl",
                                    )
                            except Exception as exc:
                                st.warning(f"컷은 저장됨. OpenDART 탐색 실패: {exc}")
                        st.success(
                            f"cutoff {cutoff_opt.cutoff:.2f} / {int(target_n)}종 확정 · "
                            f"백업 `{backup.name}`"
                        )
                        st.rerun()

        return cutoff_opt.cutoff, int(target_n)
