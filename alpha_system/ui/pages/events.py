"""이벤트/갱신 렌더 헬퍼 — 화면 진입점은 approval.render_approval."""

from __future__ import annotations

from datetime import date

import streamlit as st

from alpha_system.journal import append_record
from alpha_system.ui.services.approval_chrome import (
    ap_chips,
    ap_copy,
    ap_freshness_table,
    ap_subhead,
)
from alpha_system.ui.services.auto_journal import journal_go_live_blocked
from alpha_system.ui.services.background_job import job_is_busy
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.go_live_gate import block_go_live_reasons
from alpha_system.ui.services.runtime_state import RuntimeState
from alpha_system.ui.services.ui_copy import copy_get


def _render_killswitch_watch(
    ctx: DashboardContext,
    *,
    t2_ids: list[str],
    as_of: date,
) -> None:
    """Official RSS candidates. Does not fire gates or write target_portfolio."""
    from alpha_system.ui.services.killswitch_watch import (
        MANUAL_SEARCH_LINKS,
        event_label,
        load_watch,
        refresh_killswitch_watch,
        watch_is_stale,
    )

    snap = load_watch(ctx.root)
    stale = watch_is_stale(snap)
    with st.container(border=True):
        ap_subhead(
            ap_copy("weekly_watch_title", default="공식 출처 탐색"),
            desc=ap_copy("weekly_watch_desc"),
        )
        if snap and snap.fetched_at:
            stamp = snap.fetched_at.replace("T", " ")[:19]
            st.caption(
                ap_copy(
                    "weekly_watch_as_of",
                    default="마지막 탐색 {when} · 후보 {n}건",
                    when=stamp,
                    n=len(snap.hits),
                )
            )
        elif stale:
            st.caption(ap_copy("weekly_watch_never", default="아직 탐색하지 않았습니다."))
        from alpha_system.ui.services.approval_chrome import (
            refresh_action_button,
            refresh_rail,
        )

        refresh_rail(
            title=ap_copy("weekly_watch_rail", default="공식 출처 RSS 갱신"),
            hint=ap_copy(
                "weekly_watch_rail_hint",
                default="킬스위치 후보 탐색 · 점수·target 불변",
            ),
        )
        col_run, _ = st.columns((1, 2))
        with col_run:
            if refresh_action_button(
                ap_copy("weekly_watch_run", default="공식 출처 탐색"),
                key="btn_killswitch_watch",
                disabled=job_is_busy(ctx.root),
                primary=True,
            ):
                try:
                    refresh_killswitch_watch(
                        ctx.root,
                        as_of=as_of,
                        event_ids=t2_ids,
                    )
                    st.success(ap_copy("weekly_watch_ok", default="탐색을 마쳤습니다. 아래 후보를 확인하세요."))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        hits = snap.hit_models() if snap else ()
        if snap and not hits:
            st.caption(ap_copy("weekly_watch_empty"))
            fail = [f for f in (snap.feeds or []) if not f.get("ok")]
            if fail:
                st.caption(
                    "피드 실패: "
                    + ", ".join(f"{f.get('label') or f.get('id')} ({f.get('error') or '오류'})" for f in fail[:4])
                )
        for hit in hits:
            label = event_label(hit.event_id)
            st.markdown(f"**{label}** · {hit.title}")
            st.caption(f"{hit.published or '날짜 없음'} · {hit.note}")
            st.caption(hit.url)
        with st.expander(ap_copy("weekly_watch_manual", default="공식 검색 페이지 (직접 열기)"), expanded=False):
            for name, url in MANUAL_SEARCH_LINKS:
                st.markdown(f"- [{name}]({url})")


def _render_opendart_weekly_hook(ctx: DashboardContext) -> None:
    """② 이번 주: stale이면 OpenDART 증분 1회 자동 · 실패 시 상단 버튼."""
    from alpha_system.ui.services.approval_chrome import (
        ap_subhead,
        refresh_action_button,
        refresh_rail,
    )
    from alpha_system.ui.services.cecs_opendart_pack import (
        load_opendart_watch,
        watch_needs_refresh,
    )
    from alpha_system.ui.services.refresh import (
        ensure_opendart_incremental_if_stale,
        watch_pool_tickers,
    )
    from alpha_system.screen_book import source_data_dir

    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    tickers = watch_pool_tickers(ctx.root, market=market, top_n=30)
    data_dir = source_data_dir(ctx.root, market)
    snap = load_opendart_watch(ctx.root, data_dir=data_dir)
    stale = watch_needs_refresh(snap, tickers) if tickers else False
    sig = f"{market}:{len(tickers)}:{','.join(tickers[:5])}"
    auto_key = f"_opendart_weekly_auto_{sig}"

    with st.container(border=True):
        ap_subhead(
            ap_copy("opendart_weekly_title", default="OpenDART 관찰"),
            desc=ap_copy(
                "opendart_weekly_desc",
                default=(
                    "정성 Review용 공시 캐시 · 만료·종목변경 시 증분 자동 · "
                    "점수·target 불변"
                ),
            ),
        )
        if not tickers:
            st.caption(
                ap_copy(
                    "opendart_weekly_no_pool",
                    default="관찰 풀 없음 · ① 정량 갱신 후 다시 오세요.",
                )
            )
            return
        if snap and getattr(snap, "missing_key", False):
            st.warning(
                ap_copy(
                    "opendart_weekly_no_key",
                    default="Open DART API 키가 없습니다. 설정에 키를 넣으세요.",
                )
            )
            return
        if not stale:
            when = (getattr(snap, "fetched_at", None) or "—").replace("T", " ")[:19]
            st.caption(
                ap_copy(
                    "opendart_weekly_fresh",
                    default="관찰 캐시 최신 · {when} · {n}종",
                    when=when,
                    n=len(tickers),
                )
            )
            return

        st.warning(
            ap_copy(
                "opendart_weekly_stale",
                default="캐시 만료 또는 종목 집합 변경 · 증분 갱신 필요",
            )
        )
        refresh_rail(
            title=ap_copy("opendart_weekly_rail", default="OpenDART 증분"),
            hint=ap_copy(
                "opendart_weekly_rail_hint",
                default="만료·신규만 호출 · 전체 재탐색 아님 · target 불변",
            ),
        )

        auto_state = st.session_state.get(auto_key)
        if auto_state is None:
            # First visit while stale → auto incremental once
            try:
                with st.spinner(
                    ap_copy(
                        "opendart_weekly_spin",
                        default="OpenDART 증분 갱신 중…",
                    )
                ):
                    result = ensure_opendart_incremental_if_stale(
                        ctx.root, market=market, force=False
                    )
                status = str(result.get("status") or "")
                if status in {"refreshed", "fresh"}:
                    st.session_state[auto_key] = "ok"
                    st.success(
                        ap_copy(
                            "opendart_weekly_ok",
                            default="OpenDART 증분 완료 · {when}",
                            when=str(result.get("fetched_at") or "")[:19],
                        )
                    )
                    st.rerun()
                elif status == "missing_key":
                    st.session_state[auto_key] = "missing_key"
                    st.warning(
                        ap_copy(
                            "opendart_weekly_no_key",
                            default="Open DART API 키가 없습니다. 설정에 키를 넣으세요.",
                        )
                    )
                else:
                    st.session_state[auto_key] = "fail"
                    st.error(str(result.get("error") or status or "증분 실패"))
            except Exception as exc:  # noqa: BLE001
                st.session_state[auto_key] = "fail"
                st.error(str(exc))

        if refresh_action_button(
            ap_copy("opendart_weekly_btn", default="증분 갱신"),
            key=f"btn_opendart_weekly_incr_{market}",
            disabled=job_is_busy(ctx.root),
            primary=True,
        ):
            try:
                with st.spinner(
                    ap_copy(
                        "opendart_weekly_spin",
                        default="OpenDART 증분 갱신 중…",
                    )
                ):
                    result = ensure_opendart_incremental_if_stale(
                        ctx.root, market=market, force=True
                    )
                if result.get("status") in {"refreshed", "fresh"}:
                    st.session_state[auto_key] = "ok"
                    st.success(
                        ap_copy(
                            "opendart_weekly_ok",
                            default="OpenDART 증분 완료 · {when}",
                            when=str(result.get("fetched_at") or "")[:19],
                        )
                    )
                    st.rerun()
                elif result.get("status") == "missing_key":
                    st.warning(
                        ap_copy(
                            "opendart_weekly_no_key",
                            default="Open DART API 키가 없습니다. 설정에 키를 넣으세요.",
                        )
                    )
                else:
                    st.error(str(result.get("error") or "증분 실패"))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def _render_weekly_qual(
    ctx: DashboardContext,
    *,
    focused: bool = False,
) -> None:
    """Official RSS + OpenDART stale auto-incr — no operator draft form."""
    del focused
    t2_ids = list(ctx.cfg.t2_event_ids())
    as_of = ctx.as_of if isinstance(ctx.as_of, date) else date.today()
    if not t2_ids:
        st.error("제도 이벤트 목록이 비어 있습니다. 설정 `qual_gates.t2_event_ids`를 확인하세요.")
        return
    _render_opendart_weekly_hook(ctx)
    _render_killswitch_watch(ctx, t2_ids=t2_ids, as_of=as_of)


def _render_go_live(ctx: DashboardContext) -> None:
    if not ctx.pre_launch and ctx.effective_go_live is not None:
        st.info(
            copy_get(
                "go_live",
                "already_live",
                date=ctx.effective_go_live.isoformat(),
            )
        )
        return

    cutoff = None
    if ctx.checklist is not None:
        cutoff = next((i for i in ctx.checklist.items if i.key == "score_cutoff"), None)
    if cutoff and not cutoff.ok:
        ap_chips([(ap_copy("chip_cutoff_wait"), "wait")])

    st.warning(copy_get("go_live", "warn"))
    c1 = st.checkbox(copy_get("go_live", "confirm_1"), key="gl_c1")
    c2 = st.checkbox(copy_get("go_live", "confirm_2"), key="gl_c2")
    live_date = st.date_input("가동 기준일", value=date.today(), key="gl_date")
    if st.button(
        "가동 선언",
        disabled=not (c1 and c2),
        key="gl_submit",
        width="stretch",
    ):
        blocking = block_go_live_reasons(ctx.checklist) if ctx.checklist else []
        if blocking:
            msg = copy_get(
                "checklist",
                "go_live_blocked",
                items="; ".join(blocking),
            )
            journal_go_live_blocked(as_of=date.today(), items=blocking)
            st.error(msg)
            return
        iso = live_date.isoformat()
        append_record(
            action_kind="GO_LIVE_DECLARE",
            as_of=live_date,
            subject="*",
            rationale="operator go-live declaration",
            trigger_snapshot={"go_live_date": iso},
            payload={"go_live_date": iso},
        )
        runtime = RuntimeState.load(ctx.root / "data" / "alpha_dashboard_runtime.json")
        runtime.go_live_date = iso
        runtime.save(ctx.root / "data" / "alpha_dashboard_runtime.json")
        st.success(copy_get("go_live", "success", date=iso))
        st.rerun()


def _render_pension_confirm_strip(ctx: DashboardContext) -> None:
    """확인① 아래 수급 한눈 — Review-only · 상세는 나침반."""
    from alpha_system.ui.services.pension_briefing_board import (
        PENSION_BRIEFING_CSS,
        pension_confirm_strip_html,
    )
    from alpha_system.ui.services.pension_briefing_bridge import fetch_pension_briefing
    from alpha_system.ui.services.pension_briefing_refresh import (
        load_pension_refresh_status,
    )

    st.markdown(f"<style>{PENSION_BRIEFING_CSS}</style>", unsafe_allow_html=True)
    view = fetch_pension_briefing(
        alpha_root=ctx.root,
        proposal_rows=getattr(ctx, "portfolio_rows", None),
        holdings_rows=getattr(ctx, "ops_portfolio_rows", None),
    )
    status = load_pension_refresh_status(ctx.root)
    st.markdown(
        pension_confirm_strip_html(view, refresh_status=status),
        unsafe_allow_html=True,
    )


def _render_data_refresh(ctx: DashboardContext) -> None:
    ap_subhead(
        ap_copy("quant_refresh_title", default="중기·단기 정량·정성 통합 갱신"),
        desc=ap_copy(
            "quant_refresh_desc",
            default=(
                "한 시장당 버튼 한 번=중기+단기 점수·가격·RSS·OpenDART·수급. "
                "제안은 포트폴리오 · target·순위 자동변경 없음."
            ),
        ),
    )
    ap_freshness_table(
        ctx.source_status,
        market=str(getattr(ctx, "screen_market", None) or "KOSPI"),
    )
    from alpha_system.screen_book import market_label

    mkt_lab = market_label(getattr(ctx, "screen_market", None))
    label = ap_copy(
        "quant_refresh_btn",
        default="{m} 중기·단기 정량·정성 한 번에",
        m=mkt_lab,
    )
    # 버튼 키는 시장만 — 중기+단기 한 번에
    if st.button(
        label,
        type="primary",
        key=f"btn_quant_unified_mid_short_{getattr(ctx, 'screen_market', 'KOSPI')}",
        use_container_width=True,
        disabled=job_is_busy(ctx.root),
    ):
        from alpha_system.ui.services.background_job import start_dashboard_job

        err = start_dashboard_job(
            ctx.root,
            "quant",
            collect_scope="liquid",
            market=str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI"),
        )
        if err:
            st.warning(err)
        else:
            st.rerun()
    from alpha_system.ui.services.refresh_progress_ui import render_inline_job_progress

    render_inline_job_progress(ctx.root, kind="quant")
    from alpha_system.ui.services.refresh import quant_refresh_when

    when = quant_refresh_when(ctx.root, market=getattr(ctx, "screen_market", None))
    if when:
        st.caption(
            ap_copy(
                "quant_refresh_as_of",
                default="마지막 중기·단기 통합 갱신 {when}",
                when=when,
            )
            + " · "
            + ap_copy(
                "quant_refresh_foot",
                default=(
                    "동일 alpha_scores · 가격 mid+short · RSS · "
                    "OpenDART 증분 · 심층 · PH-CVS 정밀 · 형제 수급"
                ),
            )
        )
    else:
        st.caption(
            ap_copy(
                "quant_refresh_never",
                default="아직 중기·단기 통합 갱신을 실행하지 않았습니다.",
            )
        )
    _render_pension_confirm_strip(ctx)
