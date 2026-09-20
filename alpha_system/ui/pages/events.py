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
        col_run, _ = st.columns((1, 2))
        with col_run:
            if st.button(
                ap_copy("weekly_watch_run", default="공식 출처 탐색"),
                key="btn_killswitch_watch",
                use_container_width=True,
                disabled=job_is_busy(ctx.root),
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


def _render_weekly_qual(
    ctx: DashboardContext,
    *,
    focused: bool = False,
) -> None:
    """Official RSS candidates only — no operator draft or approval form."""
    del focused
    t2_ids = list(ctx.cfg.t2_event_ids())
    as_of = ctx.as_of if isinstance(ctx.as_of, date) else date.today()
    if not t2_ids:
        st.error("제도 이벤트 목록이 비어 있습니다. 설정 `qual_gates.t2_event_ids`를 확인하세요.")
        return
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


def _render_data_refresh(ctx: DashboardContext) -> None:
    ap_subhead(
        ap_copy("quant_refresh_title"),
        desc=ap_copy("quant_refresh_desc"),
    )
    ap_freshness_table(ctx.source_status)
    from alpha_system.screen_book import market_label

    label = f"{market_label(getattr(ctx, 'screen_market', None))} 정량 갱신"
    if st.button(
        label,
        type="primary",
        key=f"btn_quant_snapshot_refresh_{getattr(ctx, 'screen_market', 'KOSPI')}",
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
    from alpha_system.ui.services.refresh import quant_refresh_when

    when = quant_refresh_when(ctx.root, market=getattr(ctx, "screen_market", None))
    if when:
        st.caption(ap_copy("quant_refresh_as_of", default="마지막 갱신 {when}", when=when))
    else:
        st.caption(
            ap_copy(
                "quant_refresh_never",
                default="아직 정량 갱신을 실행하지 않았습니다.",
            )
        )
