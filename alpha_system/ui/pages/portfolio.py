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
    GATE_REASON_KO,
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
from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.screen_market import render_screen_market_nav
from alpha_system.ui.services.screen_horizon import render_screen_horizon_nav
from alpha_system.screen_book import (
    is_kosdaq,
    is_short,
    save_kosdaq_policy,
    save_short_policy,
    target_names_band,
    watch_max,
)
from alpha_system.ui.theme_prefs import watch_row_styles

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
            "portfolio", "page_title", default="제안 · 보유"
        ),
        lead=copy_get(
            "portfolio",
            "page_lead",
            default=(
                "결정면=③제안·④보유 · ①②는 입력. "
                "Review-only · target 자동기입 없음."
            ),
        ),
    )
    render_screen_market_nav(ctx.root)
    render_screen_horizon_nav(ctx.root)
    if is_short(getattr(ctx, "screen_horizon", None)):
        _render_short_vol_budget_banner(ctx)
    if not (ctx.scoreboard_rows or []):
        _render_status_card(
            "이 시장 정량이 없습니다. 확인 → ① 숫자에서 정량 갱신 · "
            "단기 북은 같은 스냅샷을 재랭크합니다.",
            tone="warn",
        )
    # 워크플로 ①→②→③→④ 유지 · 시각 무게만 ③·④ (pf-tier-1)
    st.markdown('<div class="pf-tier-2">', unsafe_allow_html=True)
    preview_cutoff, preview_n = _render_cutoff_bar(ctx)
    _render_watch_pool(ctx, preview_cutoff, preview_n)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="pf-tier-1">', unsafe_allow_html=True)
    _render_proposal_book(
        ctx,
        proposal_eligible_sorter=proposal_eligible_sorter,
        proposal_final_sort_label=proposal_final_sort_label,
    )
    _render_holdings_book(ctx)
    st.markdown("</div>", unsafe_allow_html=True)
    _render_phcvs_watch(ctx)


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
    """External PH-CVS observation list — always open, Review-only."""
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
    title = copy_get("portfolio", "sec_phcvs", default="PH-CVS 추적")
    attn_n = sum(1 for r in board.rows if _is_attention(r))
    chips: list[tuple[str, str]] = []
    if attn_n:
        chips.append((f"지금 볼 것 {attn_n}", "warn"))
    else:
        chips.append(("즉시 Review 없음", "muted"))
    if board.as_of_prices:
        chips.append((f"가격 {board.as_of_prices}", "muted"))
    chips.append(("Review-only", "muted"))
    with st.container(border=True):
        _render_section_head(
            title,
            summary=copy_get(
                "portfolio",
                "phcvs_caption",
                default=(
                    "상단「지금 볼 것」만 먼저 · 겹침·가격/유동 PASS · "
                    "나머지는 추적 · 현금=시드 · 매수·자동편입 없음"
                ),
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
        st.markdown(phcvs_watch_html(board), unsafe_allow_html=True)


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
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )

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
    snap = load_opendart_watch(ctx.root, data_dir=data_dir)
    auto_key = "pf_od_auto_" + ",".join(tickers)
    need = watch_needs_refresh(snap, tickers)
    if need and not st.session_state.get(auto_key):
        st.session_state[auto_key] = True
        try:
            with st.spinner("관찰 풀 OpenDART 탐색 (경영참여·최대주주)"):
                snap = refresh_opendart_proposal_watch(
                    ctx.root,
                    tickers,
                    as_of=as_of,
                    journal_path=journal,
                    data_dir=data_dir,
                )
        except Exception as exc:
            st.warning(f"OpenDART 탐색 실패: {exc}")
    if st.button("다시 탐색", key="pf_od_refetch"):
        st.session_state[auto_key] = True
        try:
            with st.spinner("관찰 풀 OpenDART 탐색 (경영참여·최대주주)"):
                snap = refresh_opendart_proposal_watch(
                    ctx.root,
                    tickers,
                    as_of=as_of,
                    journal_path=journal,
                    data_dir=data_dir,
                )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            return
    if snap is None:
        return
    if snap.missing_key:
        st.warning("Open DART API 키가 없습니다. 설정에 키를 넣은 뒤 다시 탐색하세요.")
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
    control_flags = [item for item in flags if str(item.kind) == "control_purpose"]
    other_flags = [item for item in flags if str(item.kind) != "control_purpose"]
    if not control_flags and not other_flags:
        return
    with st.expander(
        copy_get(
            "portfolio",
            "gate_memo_expand",
            default="게이트 메모 {n}건",
            n=len(flags),
        ),
        expanded=bool(control_flags),
    ):
        st.caption(
            copy_get(
                "portfolio",
                "opendart_gate_caption",
                default=(
                    "경영참여·연기금 감소는 제안에서 자동 제외. "
                    "5% 경영참여는 사다리 매수1 Review-only. target 파일 불변."
                ),
            )
        )
        for item in control_flags:
            tk = str(item.ticker).zfill(6)
            name = names.get(tk, tk)
            mark = "제안에서 제외" if tk in gated else "탐색됨"
            st.markdown(
                f"- {naver_name_chart_html(tk, name)} · 경영참여 선행 · {mark} · "
                f"사다리 매수1 검토 · {_esc(item.note)}",
                unsafe_allow_html=True,
            )
        for item in other_flags:
            tk = str(item.ticker).zfill(6)
            kind = str(item.kind)
            label = GATE_REASON_KO.get(kind, kind)
            name = names.get(tk, tk)
            mark = "제안에서 제외" if tk in gated else "탐색됨"
            st.markdown(
                f"- {naver_name_chart_html(tk, name)} · {label} · {mark} · {_esc(item.note)}",
                unsafe_allow_html=True,
            )


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
            ("최종 제안", str(n_eligible), "단기 편입 후보", "모멘텀 재랭크", "ok"),
            ("편입하지 않음", str(n_blocked), "제외", "게이트·적격 탈락", "warn"),
            ("보유", str(n_held), "④ 실보유", "유지/축소/교체", "muted"),
        ]
        yolk = ""
    else:
        tiles = [
            ("최종 제안", str(n_eligible), "편입 후보", "비중은 여기만", "ok"),
            ("편입하지 않음", str(n_blocked), "노른자 대기", "비싸거나 게이트", "warn"),
            ("보유", str(n_held), "④에서", "제안과 다를 수 있음", "muted"),
        ]
        yolk = (
            "노른자 = 「편입하지 않음」고Q(+최종 제안 고품질). "
            "④ 보유 전부 ≠ 노른자."
        )
        if quality_sort:
            yolk = "최종 제안 Q↓·하케다카↓ · " + yolk
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


def _render_proposal_book(
    ctx: DashboardContext,
    *,
    proposal_eligible_sorter: Callable[
        [list[PortfolioRow], DashboardContext], list[PortfolioRow]
    ]
    | None = None,
    proposal_final_sort_label: str | None = None,
) -> None:
    short = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        eligible = list(ctx.portfolio_rows or [])
        if proposal_eligible_sorter and eligible:
            eligible = proposal_eligible_sorter(eligible, ctx)
        blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
        held_n = len(getattr(ctx, "ops_portfolio_rows", None) or [])
        _render_section_head(
            copy_get("portfolio", "sec_proposal", default="③ 제안 종목"),
            summary=copy_get(
                "portfolio",
                "screen_book_caption_short" if short else "screen_book_caption",
                default="지도 → 편입 후보 → 대기열. 비중·실행은 사람 Review.",
            ),
            chips=[
                ("편입 = 최종 제안", "ok"),
                ("대기 = 편입하지 않음", "warn"),
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
                        "단기 배지(Review-only): 제안 밖·모멘텀 붕괴·52주 −20%=교체 · "
                        "score_m·6M·상대 약화=축소 · 정당 P/B 미사용 · 자동매도 없음"
                    ),
                )
            )
        final_heading = copy_get(
            "portfolio", "proposal_final_heading", default="최종 제안"
        )
        if proposal_final_sort_label:
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
                copy_get(
                    "portfolio",
                    "proposal_final_empty",
                    default="최종 제안이 없습니다. 합격선·점수표를 점검하세요.",
                )
            )
        else:
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix="pf_proposal",
                rows=eligible,
            )
        if blocked:
            blocked_head = copy_get(
                "portfolio", "proposal_blocked_heading", default="편입하지 않음"
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
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix="pf_blocked",
                rows=blocked,
            )


def _render_holdings_book(ctx: DashboardContext) -> None:
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
            (f"실보유 {len(held_rows)}", "muted"),
        ]
        if overlap_n:
            hold_chips.append((f"제안중 {overlap_n}", "ok"))
        hold_chips.append(("노른자는 ③ 대기열", "warn"))
        _render_section_head(
            copy_get("portfolio", "sec_holdings", default="④ 보유 종목"),
            summary=copy_get(
                "portfolio",
                "holdings_caption_short" if short else "holdings_caption",
                default="실보유 · ② 체크와 동기 · 제안과 다를 수 있음.",
            ),
            chips=hold_chips,
            tier="primary",
        )
        if short:
            st.caption(
                copy_get(
                    "portfolio",
                    "ops_cue_short_caption",
                    default=(
                        "단기 배지(Review-only): 제안 밖·모멘텀 붕괴·52주 −20%=교체 · "
                        "score_m·6M·상대 약화=축소 · 정당 P/B 미사용 · 자동매도 없음"
                    ),
                )
            )
        # 단기채 Review 비율·할 일 = 경제 나침반 playbook (중복 카드 없음)
        _render_monthly_rebal_note(ctx)
        _render_weight_action_board(ctx)
        render_portfolio_bullets(
            ctx,
            mode="full",
            key_prefix="pf_ops",
            rows=list(ctx.ops_portfolio_rows or []),
            empty_hint="실보유가 없습니다. 위 후보 30 표에서 맨 앞칸을 체크하면 여기에 표시됩니다.",
        )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_weight_action_board(ctx: DashboardContext) -> None:
    """Today's ratio to-do list above holdings — Review-only."""
    from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
    from alpha_system.ui.services.weight_action import (
        board_items,
        build_weight_actions_for_rows,
        weight_action_board_html,
    )

    rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    if not rows:
        return
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
    st.markdown(
        weight_action_board_html(board_items(pairs)),
        unsafe_allow_html=True,
    )


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
    tones = watch_row_styles(st.session_state.get("saa_ui_theme") or "dark")

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
        _render_section_head(
            copy_get("portfolio", "sec_watch", default="② 후보"),
            summary=copy_get(
                "portfolio",
                "watch_intro_short" if short_watch else "watch_intro",
                default=(
                    "관찰 풀 · 맨 앞칸 체크 = ④ 실보유 등록."
                    if short_watch
                    else "관찰 풀 · 맨 앞칸 체크 = ④ 실보유 · 표 색 = ① 컷·③ 제안 관계."
                ),
            ),
            chips=[("맨 앞칸 체크 → ④ 보유", "ok")],
            extra_html=legend,
            tier="input",
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
            for r in table_rows:
                rec = {
                    "순위": r.rank,
                    "구분": watch_tone_label(r.tone),
                    "종목": r.name,
                    "차트": naver_fchart_url(r.ticker),
                    "코드": r.ticker,
                    "점수": r.total_score,
                    "SR": r.score_sr,
                    "배당%": r.dividend_yield,
                    "하케다카": r.hakedaka or "—",
                    "섹터": r.sector or "—",
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
            held_idx = [
                i for i, r in enumerate(table_rows) if r.ticker in saved_tickers
            ]
            saved_in_30 = tuple(
                sorted(r.ticker for r in table_rows if r.ticker in saved_tickers)
            )
            sig = tuple(r.ticker for r in table_rows)
            if st.session_state.get(watch_sig) != sig:
                st.session_state.pop(watch_key, None)
                st.session_state[watch_sig] = sig
                st.session_state[watch_last] = saved_in_30

            event = st.dataframe(
                _style_watch_df(frame),
                hide_index=True,
                width="stretch",
                height=38 + 33 * len(frame),
                row_height=32,
                on_select="rerun",
                selection_mode="multi-row",
                selection_default={"selection": {"rows": held_idx}},
                key=watch_key,
                placeholder="—",
                column_config={
                    "순위": st.column_config.NumberColumn("순위", format="%d"),
                    "차트": st.column_config.LinkColumn(
                        "차트",
                        help="네이버 일봉 차트",
                        display_text="차트",
                    ),
                    "점수": st.column_config.NumberColumn("점수", format="%.2f"),
                    "SR": st.column_config.NumberColumn(
                        "SR",
                        format="%.1f",
                        help="환원 score_sr (배당·성향·자사주·연속성) · 합계 25%",
                    ),
                    "배당%": st.column_config.NumberColumn(
                        "배당%",
                        format="%.2f",
                        help="배당수익률(%) · 후보 30 안에서만 표시",
                    ),
                    "하케다카": st.column_config.TextColumn(
                        "하케다카",
                        help=(
                            "순차 게이트 · 절대 4축(순현금·자사주·최대주주·순환출자). "
                            "예: 2/4 통과 · 미측정 1 = 충족 2, 미측정 1, 나머지 불충족. "
                            "×는 ‘측정됐는데 아님’ · 미측정과 다름. "
                            "합계·환원(score_sr)과 별개 · 단기 북은 미적용."
                        ),
                    ),
                    "흡수": st.column_config.TextColumn(
                        "흡수",
                        help=(
                            "단기 Review · 거래대금≥20일평균 3배 and 1M 수익률≤+3% "
                            "(급락 −20% 미만 제외). 매집 단정 아님 · 자동매수 없음."
                        ),
                    ),
                    "PER": st.column_config.NumberColumn("PER", format="%.2f"),
                    "PBR": st.column_config.NumberColumn("PBR", format="%.2f"),
                    "ROE": st.column_config.NumberColumn("ROE", format="%.1f"),
                    "현재가": st.column_config.NumberColumn("현재가", format="%.0f"),
                    "목표가": st.column_config.NumberColumn("목표가", format="%.0f"),
                },
            )
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
            sel_rows = list(getattr(getattr(event, "selection", None), "rows", None) or [])
            sel_tickers = []
            for i in sel_rows:
                if 0 <= int(i) < len(table_rows):
                    sel_tickers.append(table_rows[int(i)].ticker)
            current = tuple(sorted(sel_tickers))
            prev = st.session_state.get(watch_last)
            if prev is None:
                st.session_state[watch_last] = saved_in_30
            elif current != prev:
                _persist_watch_holdings(ctx, list(current))
                st.session_state[watch_last] = current
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

    with st.expander("붙여넣기 · HTS 수량", expanded=False):
        text = st.text_area(
            "보유 목록",
            key="holdings_paste_text",
            height=140,
            placeholder="030200 100 45000\n021240 50 52000",
            label_visibility="collapsed",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "붙여넣기 저장",
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
                    result = upsert_kr_alpha_positions(
                        path,
                        parsed.drafts,
                        root=ctx.root,
                        replace_alpha=True,
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
