"""Portfolio page — observation 30, proposal book, ops holdings."""

from __future__ import annotations

from datetime import date as _date

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
from alpha_system.ui.services.context import DashboardContext
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
from alpha_system.ui.services.approval_chrome import ap_subhead, page_head
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.screen_market import render_screen_market_nav
from alpha_system.screen_book import is_kosdaq, save_kosdaq_policy, target_names_band, watch_max
from alpha_system.ui.theme_prefs import watch_row_styles

def _watch_session_keys(ctx: DashboardContext) -> tuple[str, str, str]:
    mkt = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    return f"pf_watch_{mkt}", f"pf_watch_{mkt}_sig", f"pf_watch_{mkt}_last"


def _reset_watch_picker(ctx: DashboardContext, tickers: list[str]) -> None:
    key, _sig, last = _watch_session_keys(ctx)
    st.session_state.pop(key, None)
    st.session_state[last] = tuple(sorted(tickers))



def render_portfolio(ctx: DashboardContext) -> None:
    consume_focus()  # confirmation CTAs land here; no sub-tabs
    if "holdings_input_open" not in st.session_state:
        st.session_state["holdings_input_open"] = True

    page_head(
        kicker=copy_get("portfolio", "page_kicker", default="포트폴리오"),
        title=copy_get("portfolio", "page_title", default="후보 · 제안 · 보유"),
        lead=copy_get(
            "portfolio",
            "page_lead",
            default=(
                "관찰 풀에서 체크하면 보유에 등록됩니다. "
                "제안은 컷·편입 수 확정. 자동매매·target 변경 없음."
            ),
        ),
    )
    render_screen_market_nav(ctx.root)
    if is_kosdaq(getattr(ctx, "screen_market", None)) and not (ctx.scoreboard_rows or []):
        st.caption(
            "이 장부는 아직 정량이 없습니다. 확인 → ① 숫자에서 「코스닥 정량 갱신」을 누르세요."
        )
    preview_cutoff, preview_n = _render_cutoff_bar(ctx)
    _render_watch_pool(ctx, preview_cutoff, preview_n)
    _render_proposal_book(ctx)
    _render_holdings_book(ctx)


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


def _render_proposal_opendart_gates(ctx: DashboardContext) -> None:
    """OpenDART on the watch pool: 경영참여 게이트 + 최대주주 + Review-only 선행 트리거."""
    from alpha_system.ui.services.cecs_opendart_pack import (
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )

    watch_rows = list(ctx.scoreboard_rows or [])
    proposal_rows = list(ctx.portfolio_rows or [])
    if not watch_rows and not proposal_rows:
        return
    tickers = [str(r.ticker).zfill(6) for r in (watch_rows or proposal_rows)]
    names = {
        str(r.ticker).zfill(6): (r.name or r.ticker)
        for r in list(watch_rows) + list(proposal_rows)
    }
    journal = ctx.root / "data" / "alpha_system_journal.jsonl"
    as_of = ctx.as_of if isinstance(ctx.as_of, _date) else _date.today()
    data_dir = ctx.data_dir
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
    path = overlay_path(ctx.data_dir)
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


def _render_proposal_book(ctx: DashboardContext) -> None:
    with st.container(border=True):
        ap_subhead(
            copy_get("portfolio", "sec_proposal", default="③ 제안 종목"),
            desc=copy_get(
                "portfolio",
                "screen_book_caption",
                default=(
                    "최종 제안만 편입 후보입니다. "
                    "점수 상위라도 게이트·목표가에 걸리면 아래 제외 칸에만 둡니다. "
                    "자동매도·target 변경 없음."
                ),
            ),
        )
        eligible = list(ctx.portfolio_rows or [])
        blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
        _render_sector_exposure(ctx)
        _render_revalidate_flags(ctx)
        _render_proposal_opendart_gates(ctx)
        _render_proposal_target_board(ctx)
        st.markdown(
            f'<div class="pf-group-kicker">'
            f'{copy_get("portfolio", "proposal_final_heading", default="최종 제안")}'
            f" · {len(eligible)}"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            copy_get(
                "portfolio",
                "proposal_final_caption",
                default="컷·게이트·목표가·하케다카를 통과한 편입 후보. 비중은 여기만입니다.",
            )
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
            st.markdown(
                f'<div class="pf-group-kicker">'
                f'{copy_get("portfolio", "proposal_blocked_heading", default="편입하지 않음")}'
                f" · {len(blocked)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                copy_get(
                    "portfolio",
                    "proposal_blocked_caption",
                    default="점수 상위이지만 적격이 아니거나 게이트로 빠진 종목. 비중 없음.",
                )
            )
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix="pf_blocked",
                rows=blocked,
            )


def _render_holdings_book(ctx: DashboardContext) -> None:
    with st.container(border=True):
        ap_subhead(
            copy_get("portfolio", "sec_holdings", default="④ 보유 종목"),
            desc=copy_get(
                "portfolio",
                "holdings_caption",
                default=(
                    "후보 30 표 맨 앞칸 체크와 동기화 · 종목 이름·차트 = 네이버 일봉 · "
                    "수량 불필요 · 자동매매·target 변경 없음"
                ),
            ),
        )
        _render_alpha_ratio_bar(ctx)
        _render_monthly_rebal_note(ctx)
        render_portfolio_bullets(
            ctx,
            mode="full",
            key_prefix="pf_ops",
            rows=list(ctx.ops_portfolio_rows or []),
            empty_hint="실보유가 없습니다. 위 후보 30 표에서 맨 앞칸을 체크하면 여기에 표시됩니다.",
        )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_alpha_ratio_bar(ctx: DashboardContext) -> None:
    """Equity vs 단기채 9:1 usage on the holdings book."""
    from alpha_system.ui.services.alpha_book_ops import (
        build_alpha_actual_map,
        load_alpha_book_ops,
    )

    policy = load_alpha_book_ops(ctx.root)
    actual = build_alpha_actual_map(ctx.root, list(ctx.ops_portfolio_rows or []), policy)
    if not actual:
        return
    cash_pct = actual.get(policy.cash_ticker, (0.0, policy.cash_name))[0]
    equity_pct = max(0.0, 100.0 - cash_pct)
    n_equity = sum(1 for tk in actual if tk != policy.cash_ticker)
    tgt_cash = policy.cash_share * 100.0
    tgt_equity = policy.equity_share * 100.0
    gap_cash = cash_pct - tgt_cash
    gap_equity = equity_pct - tgt_equity

    if abs(gap_cash) >= 20.0:
        fill = "home-usage-fill-danger"
        tone = "경보"
    elif abs(gap_cash) >= 10.0:
        fill = "home-usage-fill-warn"
        tone = "주의"
    else:
        fill = ""
        tone = "정상"

    width = max(0.0, min(100.0, equity_pct))
    st.markdown(
        '<div class="home-usage">'
        f'<div class="home-usage-meta">{_esc(tone)} · 개별주 {equity_pct:.1f}% '
        f"({n_equity}종, 목표 {tgt_equity:.0f}%) · {_esc(policy.cash_name)} "
        f"{cash_pct:.1f}% (목표 {tgt_cash:.0f}%) · 괴리 주식 {gap_equity:+.1f}%p / "
        f"단기채 {gap_cash:+.1f}%p</div>"
        '<div class="home-usage-track">'
        f'<div class="home-usage-fill {fill}" style="width:{width:.1f}%"></div>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


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
        max_rows=watch_max(getattr(ctx, "screen_market", None)),
    )
    metrics = load_watch_metrics(ctx.root, data_dir=ctx.data_dir)
    table_rows = build_watch_table_rows(
        board,
        metrics=metrics,
        extra_by_ticker=_extra_by_ticker(ctx),
        sector_labels=load_sector_labels(ctx.root),
        cutoff=preview_cutoff,
        target_n=int(preview_n),
        blocked_tickers=blocked_tickers,
    )

    with st.container(border=True):
        ap_subhead(
            copy_get("portfolio", "sec_watch", default="② 후보"),
            desc=copy_get(
                "portfolio",
                "watch_intro",
                default=(
                    "스크린 상위 관찰 풀 · 이 30종만 OpenDART 재무 보강 · "
                    "종목 이름 = 네이버 차트 · "
                    "맨 앞칸 체크 = 실보유 등록 (바로 저장) · target·자동매매 없음"
                ),
            ),
        )
        st.markdown(
            '<div class="pf-watch-legend">'
            '<span><span class="pf-swatch pf-swatch-proposal"></span>'
            f"{copy_get('portfolio', 'watch_legend_proposal', default='최종 제안')}</span>"
            '<span><span class="pf-swatch pf-swatch-eligible"></span>'
            f"{copy_get('portfolio', 'watch_legend_eligible', default='컷 통과')}</span>"
            '<span><span class="pf-swatch pf-swatch-blocked"></span>'
            f"{copy_get('portfolio', 'watch_legend_blocked', default='편입 제외')}</span>"
            '<span><span class="pf-swatch pf-swatch-watch"></span>'
            f"{copy_get('portfolio', 'watch_legend_watch', default='관찰')}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        if board.warnings:
            for w in board.warnings:
                st.caption(w)
        if board.held_outside:
            outside = " · ".join(
                f"{r.name} ({r.ticker}) {r.rank}위" for r in board.held_outside
            )
            st.warning(
                f"관찰 {watch_max(getattr(ctx, 'screen_market', None))} 밖 — "
                f"잔류하지 않음: {outside}. "
                "표에서 체크를 바꾸면 알파에서 빠집니다."
            )
        if not table_rows:
            st.info("스크린된 관찰 종목이 없습니다. 점수판·컷오프를 확인하세요.")
        else:
            records = [
                {
                    "순위": r.rank,
                    "구분": watch_tone_label(r.tone),
                    "종목": r.name,
                    "차트": naver_fchart_url(r.ticker),
                    "코드": r.ticker,
                    "점수": r.total_score,
                    "섹터": r.sector or "—",
                    "PER": r.per,
                    "PBR": r.pbr,
                    "ROE": r.roe,
                    "현재가": r.current_price,
                    "목표가": r.target_price,
                }
                for r in table_rows
            ]
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
                    "PER": st.column_config.NumberColumn("PER", format="%.2f"),
                    "PBR": st.column_config.NumberColumn("PBR", format="%.2f"),
                    "ROE": st.column_config.NumberColumn("ROE", format="%.1f"),
                    "현재가": st.column_config.NumberColumn("현재가", format="%.0f"),
                    "목표가": st.column_config.NumberColumn("목표가", format="%.0f"),
                },
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
        data_dir=ctx.data_dir,
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
    exposures = assess_sector_weight_caps(rows, data_dir=ctx.data_dir)
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
    n_min, n_max, n_default = target_names_band(getattr(ctx, "screen_market", None))
    if yaml_n < n_min or yaml_n > n_max:
        yaml_n = n_default

    mkt = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    cutoff_key = f"portfolio_cutoff_natural_break_{mkt}"
    count_key = f"portfolio_target_names_band_{mkt}"

    with st.container(border=True):
        ap_subhead(
            copy_get("portfolio", "sec_cutoff", default="① 선정 규칙"),
            desc=copy_get(
                "portfolio",
                "cutoff_caption",
                default="합격선·편입 수는 여기서 확정합니다. YAML은 확정 전까지 그대로입니다.",
            ),
        )
        if not ladder or rec is None:
            yaml_label = (
                f"{current_cutoff:.2f}" if current_cutoff is not None else "미확정"
            )
            st.caption(f"저장 컷 {yaml_label} · 편입 {current_n}종")
            st.warning("컷오프를 계산할 유효 스코어가 없습니다.")
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

        picked = st.radio(
            "점수 컷오프",
            options=break_ranks,
            format_func=lambda rank: (
                f"{by_rank[rank].cutoff:.2f} · 적격 {by_rank[rank].eligible_count}종"
                + (" · 권고" if rec is not None and rank == rec.rank_n else "")
            ),
            horizontal=True,
            key=cutoff_key,
        )
        cutoff_opt = by_rank[int(picked)]
        target_n = st.radio(
            "제안 편입 수",
            options=list(range(n_min, n_max + 1)),
            horizontal=True,
            key=count_key,
            help="컷을 통과한 종목 중 제안 북에 담을 최대 수. 표의 제안 밴드 색이 같이 바뀝니다.",
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
            overlay=load_qual_overlay(overlay_path(ctx.data_dir)),
            exclude_tickers=collect_above_justified_target_tickers_from_root(
                [s.ticker for s in preview_scores],
                ctx.root,
            ),
        )
        selected_n = sum(
            1 for a in preview_alloc.allocated if a.incremental_weight > 0
        )
        yaml_label = (
            f"{current_cutoff:.2f}" if current_cutoff is not None else "미확정"
        )
        st.caption(
            f"미리보기 컷 **{cutoff_opt.cutoff:.2f}** · "
            f"적격 **{cutoff_opt.eligible_count}종** · "
            f"편입 **{int(target_n)}종** · "
            f"제안 예상 **{selected_n}종** "
            f"(저장 {yaml_label} / {current_n}종). "
            "표 색만 바뀝니다. 확정 전 제안 북·yaml은 그대로입니다."
        )

        changed = (
            current_n != int(target_n)
            or current_cutoff is None
            or abs(float(current_cutoff) - cutoff_opt.cutoff) > 1e-9
        )
        with st.expander("이 규칙으로 확정", expanded=current_cutoff is None):
            st.caption(
                f"경계 `{cutoff_opt.boundary_ticker}` {cutoff_opt.boundary_name}"
                + (
                    f" · 바로 아래 `{cutoff_opt.next_ticker}` "
                    f"{cutoff_opt.next_name} · 갭 {cutoff_opt.margin_below:.2f}"
                    if cutoff_opt.next_ticker is not None
                    and cutoff_opt.margin_below is not None
                    else ""
                )
            )
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
                        if is_kosdaq(getattr(ctx, "screen_market", None)):
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
