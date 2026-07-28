"""Action-queue processing panels — 상황 / 근거 / 처리 (no page hop required)."""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st
import yaml

from alpha_system.entry.entry_gates import (
    check_entry_target_valuation,
    missing_entry_target_tickers,
)
from alpha_system.entry.hard_rules import block_reverse_execution
from alpha_system.entry.models import TrancheState
from alpha_system.journal import append_record
from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore, score_name
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.ui.services.action_queue import ActionItem
from alpha_system.ui.services.auto_journal import journal_data_refresh
from alpha_system.ui.services.cecs_workbench import (
    cecs_progress,
    cutoff_actions_enabled,
    generate_correlation_report,
    load_cecs_template,
)
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.go_live_gate import assess_checklist
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_RULES_PREFIX,
    FOCUS_SETTINGS_API,
    FOCUS_T2,
    FOCUS_T3_DETAIL,
    FOCUS_WEEKLY_QUAL,
    PAGE_APPROVAL,
    PAGE_EVENTS,
    PAGE_PORTFOLIO,
    PAGE_RULES,
    PAGE_SETTINGS,
    navigate,
)
from alpha_system.ui.services.portfolio_widgets import SESSION_EXPANDED, SESSION_NAV_EXPAND
from alpha_system.ui.services.refresh import run_data_refresh
from alpha_system.ui.services.t3_history_refresh import try_generate_t3_history
from alpha_system.ui.services.ui_copy import copy_get, format_tranche_label

SESSION_PANEL = "action_panel_key"


def _exit_target_tickers(ctx: DashboardContext) -> set[str]:
    path = ctx.root / "data" / "kr_alpha_exit_targets.yaml"
    if not path.exists():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    tickers = data.get("tickers") or {}
    return {str(t).zfill(6) for t in tickers if t}


def open_panel(item_key: str) -> None:
    st.session_state[SESSION_PANEL] = item_key
    st.rerun()


def close_panel() -> None:
    st.session_state.pop(SESSION_PANEL, None)
    st.rerun()


def render_active_panel(ctx: DashboardContext) -> bool:
    """Render open panel if any. Returns True when a panel is shown."""
    key = st.session_state.get(SESSION_PANEL)
    if not key:
        return False
    item = next((a for a in ctx.action_queue if a.key == key), None)
    if item is None:
        st.session_state.pop(SESSION_PANEL, None)
        return False

    st.markdown("---")
    st.subheader(f"처리 패널 · {item.title}")
    if st.button("← 큐로", key="panel_close"):
        close_panel()

    kind = item.panel_kind
    if kind == "reduce":
        _panel_reduce(ctx, item)
    elif kind == "execute":
        _panel_execute(ctx, item)
    elif kind == "checklist":
        _panel_checklist(ctx, item)
    elif kind == "data":
        _panel_data(ctx, item)
    elif kind == "swap":
        _panel_swap(ctx, item)
    elif kind == "rescore":
        _panel_rescore(ctx, item)
    else:
        st.info(item.detail)
        _aux_link_generic(ctx, item)

    st.caption(copy_get("action_panel", "principle"))
    return True


def _section(title: str, body: str) -> None:
    st.markdown(f"**[{title}]**  \n{body}")


def _panel_reduce(ctx: DashboardContext, item: ActionItem) -> None:
    ticker = str(item.payload.get("ticker") or "")
    ops = getattr(ctx, "ops_portfolio_rows", None) or []
    row = next((r for r in ops if r.ticker == ticker), None)
    if row is None:
        row = next((r for r in ctx.portfolio_rows if r.ticker == ticker), None)
    name = (row.name if row else None) or str(item.payload.get("name") or ticker)
    weight = row.weight_pct if row else float(item.payload.get("weight_pct") or 0)
    cap = row.cap_pct if row else float(item.payload.get("cap_pct") or 35)
    excess_pp = max(0.0, weight - cap)
    sleeve = _kr_alpha_sleeve_value(ctx)
    reduce_krw = sleeve * (excess_pp / 100.0) if sleeve else None

    situation = copy_get(
        "action_panel",
        "reduce_situation",
        name=name,
        weight=f"{weight:.1f}",
        cap=f"{cap:.0f}",
        excess=f"{excess_pp:.1f}",
    )
    _section("상황", situation or item.detail)
    evid = (
        f"- 종목: **{name}** (`{ticker}`)\n"
        f"- 현재 비중: **{weight:.2f}%** / cap **{cap:.0f}%**\n"
        f"- 초과분: **{excess_pp:.2f}%p**\n"
    )
    if reduce_krw is not None:
        evid += f"- 감축 필요 금액(환산): **약 {reduce_krw:,.0f}원** (kr_alpha 평가액 기준)\n"
    else:
        evid += "- 감축 필요 금액: 평가액 없음 (금액 환산 불가)\n"
    _section("근거", evid)

    st.markdown("**[처리]**")
    st.caption("증권사에서 매도한 뒤, 아래에서 기록하세요.")
    fill_price = st.number_input("체결가", min_value=0.0, value=0.0, key=f"red_px_{ticker}")
    fill_qty = st.number_input("체결 수량", min_value=0, value=0, step=1, key=f"red_qty_{ticker}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("감축 완료 기록", type="primary", key=f"red_done_{ticker}"):
            if fill_price <= 0 or fill_qty <= 0:
                st.error("체결가·수량을 입력하세요.")
            else:
                append_record(
                    action_kind="REDUCE_COMPLETE",
                    as_of=date.today(),
                    subject=ticker,
                    rationale=f"cap reduce done @ {fill_price} x {fill_qty}",
                    payload={
                        "fill_price": fill_price,
                        "fill_qty": fill_qty,
                        "weight_pct": weight,
                        "cap_pct": cap,
                        "excess_pp": excess_pp,
                        "reduce_krw_est": reduce_krw,
                    },
                )
                st.success("감축 완료가 저널에 기록되었습니다.")
                st.rerun()
    with c2:
        defer_reason = st.text_input("보류 사유 (필수)", key=f"red_defer_reason_{ticker}")
        if st.button("보류 기록", key=f"red_defer_{ticker}"):
            if not defer_reason.strip():
                st.error("보류 사유가 필수입니다 (재량 이탈 집계).")
            else:
                append_record(
                    action_kind="WARN_DISCRETIONARY",
                    as_of=date.today(),
                    subject=ticker,
                    rationale="cap reduce deferred",
                    discretionary_reason=defer_reason.strip(),
                    payload={"kind": "reduce_defer", "weight_pct": weight, "cap_pct": cap},
                )
                st.warning("보류가 재량 이탈로 저널 기록되었습니다.")
                st.rerun()

    aux = copy_get("action_panel", "full_screen_aux")
    if st.button(f"{aux} (포트폴리오)", key=f"red_full_{ticker}"):
        st.session_state[SESSION_NAV_EXPAND] = ticker
        st.session_state[SESSION_EXPANDED] = ticker
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_PORTFOLIO)


def _panel_execute(ctx: DashboardContext, item: ActionItem) -> None:
    note = item.payload.get("note")
    tid_raw = item.payload.get("tranche_id")
    if tid_raw is None and note:
        _section("상황", item.detail)
        _section("근거", f"- 대기 메모: {note}")
        st.markdown("**[처리]**")
        st.caption("트랜치 ID가 없는 대기 항목입니다. 규칙/이벤트에서 확인하세요.")
        if st.button("전체 화면에서 보기 (규칙)", key=f"ex_note_full_{item.key}"):
            st.session_state.pop(SESSION_PANEL, None)
            navigate(PAGE_RULES)
        return

    tid = str(tid_raw or "T1")
    label = format_tranche_label(tid)
    status = next(
        (
            s
            for s in ctx.entry_eval.statuses
            if (s.tranche_id.value if hasattr(s.tranche_id, "value") else str(s.tranche_id))
            == tid
        ),
        None,
    )

    hard_block_reason: Optional[str] = None
    if status is None:
        hard_block_reason = "트랜치 상태를 찾을 수 없습니다."
    elif status.state in (TrancheState.FROZEN, TrancheState.EXPIRED, TrancheState.EXECUTED):
        hard_block_reason = f"현재 상태={status.state.value} — 추가 집행 불가"
    else:
        blocked = block_reverse_execution(
            cfg=ctx.cfg,
            tranche_id=TrancheId(tid),
            state=status.state,
            trigger_met=bool(status.trigger_met),
            weight=status.weight,
            as_of=ctx.as_of,
        )
        if blocked is not None:
            hard_block_reason = blocked.reason
        elif not status.trigger_met:
            hard_block_reason = "트리거 미충족 — 집행 불가"

    budget = float(ctx.cfg.tranches[tid].weight)
    capital_frac = float(ctx.cfg.capital.max_fraction_of_total_assets)
    alpha_book_krw, book_note = _alpha_book_krw(ctx)
    tranche_krw = (alpha_book_krw * budget) if alpha_book_krw is not None else None

    if tranche_krw is not None:
        situation = copy_get(
            "action_panel",
            "execute_situation",
            name=label,
            amount=f"{tranche_krw:,.0f}원",
        )
    else:
        situation = copy_get(
            "action_panel",
            "execute_situation_no_krw",
            name=label,
            pct=f"{budget * 100:.0f}",
        )
    _section("상황", situation)

    evid = (
        f"- 트랜치: **{label}**\n"
        f"- 트랜치 비중(예산): **{budget * 100:.0f}%** of alpha book "
        f"(총자산 알파 한도 {capital_frac * 100:.0f}% 내)\n"
    )
    if alpha_book_krw is not None:
        evid += f"- 알파 북 환산: **약 {alpha_book_krw:,.0f}원** ({book_note})\n"
        evid += f"- 이번 트랜치 집행 대상: **약 {tranche_krw:,.0f}원**\n"
    else:
        evid += f"- 알파 북 환산: 불가 ({book_note})\n"

    alloc_lines, blocked_sizing, suggested = _sizing_excerpt(ctx, tid, tranche_krw=tranche_krw)
    evid += alloc_lines
    from alpha_system.entry.scale_in import build_scale_in_plan

    scale_plan = build_scale_in_plan(date.today())
    evid += (
        f"- 종목 분할매수(SCALE_IN): **{scale_plan.n_legs}회 균등** "
        f"(1회차 ≤{scale_plan.max_single_day_fraction:.0%} of 종목 배분). "
        "한날에 전액 투입 금지 — `docs/SCALE_IN_OPS_RULE.md`\n"
    )
    _section("근거", evid)

    st.markdown("**[처리]**")
    if hard_block_reason:
        st.error(copy_get("hard_rule", "reverse_blocked", why=hard_block_reason))
        st.caption("하드 룰·상태 제약 — 집행 기록 버튼이 없습니다.")
    else:
        if blocked_sizing:
            st.warning(blocked_sizing)
        st.caption("증권사에서 배분안대로 매수한 뒤, 종목별 체결을 기록하세요.")
        target_ok = _exit_target_tickers(ctx)
        waiting = [
            a["ticker"]
            for a in suggested
            if a.get("ticker") and str(a["ticker"]).zfill(6) not in target_ok
        ]
        if waiting and ctx.cfg.exit.entry_require_target_valuation:
            st.warning(
                "목표가 미승인 대기 후보(편입 차단): "
                + ", ".join(f"`{t}`" for t in waiting)
                + " — 다음 주 통합 보고서(E) 승인 전까지 체결 기록 불가"
            )
        tickers = [a["ticker"] for a in suggested] if suggested else _eligible_tickers(ctx)[:8]
        for tkr in tickers:
            sug = next((a for a in suggested if a["ticker"] == tkr), None)
            title = f"체결 입력 · {tkr}"
            if sug and sug.get("krw") is not None:
                title += f" (배분 약 {sug['krw']:,.0f}원)"
            with st.expander(title, expanded=False):
                if sug:
                    leg_krw = (
                        float(sug["krw"]) * scale_plan.max_single_day_fraction
                        if sug.get("krw") is not None
                        else None
                    )
                    cap = (
                        f" · 1회차 한도 약 {leg_krw:,.0f}원"
                        if leg_krw is not None
                        else ""
                    )
                    st.caption(
                        f"증분 {sug['incr_pct']:.2f}%p"
                        + (f" · 약 {sug['krw']:,.0f}원" if sug.get("krw") is not None else "")
                        + cap
                    )
                tk = str(tkr).zfill(6)
                missing = missing_entry_target_tickers(
                    ctx.cfg,
                    entry_tickers=[tk],
                    has_target_by_ticker={tk: tk in target_ok},
                )
                if missing:
                    blocked_tv, tv_detail = check_entry_target_valuation(
                        ctx.cfg,
                        ticker=tk,
                        has_target_valuation=tk in target_ok,
                    )
                    st.error(
                        "대기 후보 — 목표가 승인 전 편입 차단. "
                        f"({tv_detail if blocked_tv else missing[0]})"
                    )
                    continue
                px = st.number_input(
                    "체결가", min_value=0.0, value=0.0, key=f"ex_px_{tid}_{tkr}"
                )
                qty = st.number_input(
                    "수량", min_value=0, value=0, step=1, key=f"ex_qty_{tid}_{tkr}"
                )
                if st.button("이 종목 집행 기록", key=f"ex_save_{tid}_{tkr}"):
                    if px <= 0 or qty <= 0:
                        st.error("체결가·수량 필요")
                    else:
                        # Re-check via same SoT as attempt_execute before journaling.
                        again = missing_entry_target_tickers(
                            ctx.cfg,
                            entry_tickers=[tk],
                            has_target_by_ticker={tk: tk in target_ok},
                        )
                        if again:
                            st.error("목표가 미승인 — 체결 기록 차단")
                            continue
                        fill_krw = float(px) * float(qty)
                        if sug and sug.get("krw") is not None:
                            from alpha_system.entry.scale_in import reject_full_dump

                            frac = fill_krw / float(sug["krw"]) if float(sug["krw"]) else 0.0
                            dump_reason = reject_full_dump(
                                requested_fraction_of_name_budget=frac,
                                n_legs=scale_plan.n_legs,
                            )
                            if dump_reason:
                                st.error(
                                    dump_reason
                                    + f" (체결 {fill_krw:,.0f}원 / 배분 {float(sug['krw']):,.0f}원)"
                                )
                                continue
                        append_record(
                            action_kind="TRANCHE_EXEC_FILL",
                            as_of=date.today(),
                            subject=tkr,
                            rationale=f"{tid} fill",
                            payload={
                                "tranche_id": tid,
                                "fill_price": px,
                                "fill_qty": qty,
                                "suggested_krw": sug.get("krw") if sug else None,
                                "scale_in_leg": 1,
                                "scale_in_n_legs": scale_plan.n_legs,
                                "scale_in_max_frac": scale_plan.max_single_day_fraction,
                                "leg1_krw_cap": (
                                    float(sug["krw"]) * scale_plan.max_single_day_fraction
                                    if sug and sug.get("krw") is not None
                                    else None
                                ),
                                "entry_target_gate": "ok",
                            },
                        )
                        st.success("집행 기록이 저널에 저장되었습니다.")
                        st.rerun()
        if st.button(f"{tid} 트랜치 집행 일괄 확인 기록", key=f"ex_ack_{tid}"):
            ack_tickers = [
                str(a["ticker"]).zfill(6)
                for a in suggested
                if a.get("ticker")
            ]
            has_map = {t: t in target_ok for t in ack_tickers}
            # Same SoT as attempt_execute (empty list = no names left to gate).
            ack_missing = missing_entry_target_tickers(
                ctx.cfg,
                entry_tickers=ack_tickers,
                has_target_by_ticker=has_map,
            )
            if ack_missing:
                st.error(
                    "목표가 미승인 대기 후보가 남아 일괄 확인 불가 — "
                    + "; ".join(ack_missing)
                )
            else:
                append_record(
                    action_kind="TRANCHE_EXEC_ACK",
                    as_of=date.today(),
                    subject=tid,
                    rationale=(
                        "operator acknowledged tranche execution "
                        "(fills may be partial); entry_target_gate=missing_entry_target_tickers"
                    ),
                    payload={
                        "tranche_id": tid,
                        "tranche_krw_est": tranche_krw,
                        "entry_tickers": ack_tickers,
                    },
                )
                st.success("트랜치 집행 확인이 저널에 기록되었습니다.")
                st.rerun()

    aux = copy_get("action_panel", "full_screen_aux", default="전체 화면에서 보기")
    if st.button(f"{aux} (규칙/이벤트)", key=f"ex_full_{tid}"):
        st.session_state.pop(SESSION_PANEL, None)
        if tid == "T2":
            navigate(PAGE_EVENTS, focus=FOCUS_T2)
        elif tid == "T3":
            hist = ctx.root / "data" / "kospi_market_pbr_history.csv"
            navigate(
                PAGE_EVENTS,
                focus=FOCUS_T3_DETAIL if hist.exists() else FOCUS_DATA_REFRESH,
            )
        else:
            navigate(PAGE_RULES, focus=f"{FOCUS_RULES_PREFIX}{tid}")


def _panel_checklist(ctx: DashboardContext, item: ActionItem) -> None:
    check_key = str(item.payload.get("check_key") or item.key.replace("check_", ""))
    hit = None
    if ctx.checklist is not None:
        hit = next((c for c in ctx.checklist.items if c.key == check_key), None)
    if check_key == "cecs_final":
        _panel_checklist_cecs(ctx, item)
    elif check_key == "score_cutoff":
        _panel_checklist_cutoff(ctx, item)
    elif check_key == "t3_history":
        _panel_checklist_t3(ctx, item)
    else:
        _section("상황", item.detail)
        _section(
            "근거",
            f"- 미충족: **{hit.title if hit else item.title}**\n"
            f"- 이유: {hit.why if hit else item.detail}\n"
            f"- 해결 경로: {hit.todo if hit else '규칙 화면에서 확인'}",
        )
        st.markdown("**[처리]**")
        _render_checklist_recheck(ctx, check_key)


def _panel_checklist_cecs(ctx: DashboardContext, item: ActionItem) -> None:
    path = ctx.root / "data" / "cecs_manual_scoring_template.csv"
    progress = cecs_progress(path)
    frame = load_cecs_template(path)
    draft = frame[~frame["status"].str.lower().eq("final")].copy()
    draft["_held"] = draft["is_held"].map(
        lambda value: str(value).strip().lower() in {"true", "1", "yes"}
    )
    draft = draft.sort_values(by=["_held", "rank"], ascending=[False, True])
    names = [
        f"{row['name']}({row['ticker']}){' · 보유' if row['_held'] else ''}"
        for _, row in draft.head(10).iterrows()
    ]
    _section(
        "상황",
        copy_get(
            "checklist_panel",
            "cecs_situation",
            final=progress.final,
            total=progress.total,
        ),
    )
    _section(
        "근거",
        f"- final: **{progress.final}/{progress.total}**\n"
        f"- 미채점: **{len(draft)}종**\n"
        + ("\n".join(f"  - {name}" for name in names) if names else "  - 없음"),
    )
    st.markdown("**[처리]**")
    first = str(draft.iloc[0]["ticker"]) if not draft.empty else None
    if st.button(
        "결재함에서 CECS 승인",
        type="primary",
        disabled=first is None,
        key="chk_cecs_start",
    ):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(
            PAGE_APPROVAL,
            focus=FOCUS_WEEKLY_QUAL,
        )
    _render_checklist_recheck(ctx, "cecs_final")


def _panel_checklist_cutoff(ctx: DashboardContext, item: ActionItem) -> None:
    cecs_path = ctx.root / "data" / "cecs_manual_scoring_template.csv"
    progress = cecs_progress(cecs_path)
    factor_path = ctx.root / "alpha_portfolio" / "data" / "output" / "alpha_scores.csv"
    cecs_ready = progress.total >= 30 and progress.final >= progress.total
    ready = cutoff_actions_enabled(progress, factor_exists=factor_path.exists())
    report_path = ctx.root / "docs" / f"alpha_factor_correlation_{ctx.as_of.isoformat()}.md"
    report_key = "cutoff_correlation_status"

    _section("상황", copy_get("checklist_panel", "cutoff_situation"))
    _section(
        "근거",
        f"- CECS: **{progress.final}/{progress.total}**\n"
        f"- 팩터 CSV: **{'준비됨' if factor_path.exists() else '없음'}** "
        f"(`{factor_path.relative_to(ctx.root)}`)\n"
        f"- 상관 리포트: **{'생성 가능' if ready and factor_path.exists() else '대기'}**",
    )
    st.markdown("**[처리]**")
    if not cecs_ready:
        st.info(
            copy_get(
                "checklist_panel",
                "cutoff_locked",
                final=progress.final,
                total=progress.total,
            )
        )
        st.button(
            "상관 리포트 생성",
            disabled=True,
            key="cutoff_corr_disabled",
        )
        return
    if not factor_path.exists():
        st.error("팩터 CSV가 없어 상관 리포트를 생성할 수 없습니다.")
        return

    if st.button("상관 리포트 생성", type="primary", key="cutoff_corr_generate"):
        try:
            report, path = generate_correlation_report(
                cecs_path=cecs_path,
                factor_path=factor_path,
                output_path=report_path,
                as_of=ctx.as_of,
            )
            st.session_state[report_key] = {
                "status": report.status,
                "path": str(path),
                "n_names": report.n_names,
                "high_pairs": [
                    (pair.factor_a, pair.factor_b, pair.rho, pair.n)
                    for pair in report.high_pairs
                ],
                "skip_reasons": report.skip_reasons,
            }
        except Exception as exc:
            st.error(str(exc))

    state = st.session_state.get(report_key)
    if not state:
        return
    st.markdown(
        f"- 리포트: `{state['path']}`\n"
        f"- 상태: **{state['status']}** / n={state['n_names']}"
    )
    if state["skip_reasons"]:
        st.error("; ".join(state["skip_reasons"]))
        return
    if state["high_pairs"]:
        st.caption(
            "높은 상관: "
            + ", ".join(
                f"{a}↔{b} ρ={rho:.3f} (n={n})"
                for a, b, rho, n in state["high_pairs"]
            )
        )
    else:
        st.caption("임계값 이상의 높은 상관 쌍이 없습니다.")

    st.info(copy_get("checklist_panel", "cutoff_absolute_help"))
    current = ctx.cfg.scoring.score_cutoff
    target_n = int(ctx.cfg.sizing.target_names)
    if current is None:
        st.warning(
            "score_cutoff가 아직 미확정입니다. "
            "포트폴리오 화면에서 절대 컷오프 → 편입 수(5~8) 순으로 확정하세요."
        )
    else:
        st.markdown(
            f"- 현재 `score_cutoff`: **{current:.2f}**\n"
            f"- 현재 `target_names`: **{target_n}종** (5~8 밴드)"
        )
    if st.button(
        "포트폴리오에서 절대 컷오프·편입 수 확정",
        type="primary",
        key="cutoff_goto_portfolio",
    ):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_PORTFOLIO)
    _render_checklist_recheck(ctx, "score_cutoff")


def _panel_checklist_t3(ctx: DashboardContext, item: ActionItem) -> None:
    _section("상황", copy_get("checklist_panel", "t3_situation"))
    _section(
        "근거",
        "- 자동 산출: KRX/PyKRX KOSPI 지수 일별 PBR → 월말 리샘플 (약 10년)\n"
        "- 필요: **설정** 메뉴에 저장된 KRX_ID/KRX_PW\n"
        "- 저장 경로: `data/kospi_market_pbr_history.csv`\n"
        "- 자동 산출 불가 시 동일 열(`month_end`, `market_pbr`)의 CSV 수동 적재",
    )
    st.markdown("**[처리]**")
    if st.button("자동 산출 시도", type="primary", key="t3_history_generate"):
        with st.spinner("KRX/PyKRX에서 월간 PBR 이력을 확인 중…"):
            result = try_generate_t3_history(ctx.root, today=ctx.as_of)
        append_record(
            action_kind="T3_HISTORY_REFRESH",
            as_of=ctx.as_of,
            subject="KOSPI",
            rationale=result.message,
            payload={"ok": result.ok, "rows": result.rows},
        )
        if result.ok:
            st.success(result.message)
            st.session_state.pop(SESSION_PANEL, None)
            st.rerun()
        else:
            st.error(result.message)
            st.caption("수동 경로: data/kospi_market_pbr_history.csv")
            if st.button("설정에서 KRX 저장", key="t3_goto_settings"):
                st.session_state.pop(SESSION_PANEL, None)
                navigate(PAGE_SETTINGS, focus=FOCUS_SETTINGS_API)
    _render_checklist_recheck(ctx, "t3_history")


def _render_checklist_recheck(ctx: DashboardContext, check_key: str) -> None:
    if st.button("다시 확인", key=f"chk_re_{check_key}"):
        fresh = assess_checklist(
            ctx.cfg,
            root=ctx.root,
            go_live_date=ctx.effective_go_live,
        )
        append_record(
            action_kind="CHECKLIST_RECHECK",
            as_of=date.today(),
            subject=check_key,
            rationale="operator recheck",
            payload={
                "done": fresh.done,
                "total": fresh.total,
                "ok": all(i.ok for i in fresh.items if i.key == check_key),
            },
        )
        st.rerun()

    if st.button("전체 화면에서 보기 (규칙)", key=f"chk_full_{check_key}"):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_RULES)


def _panel_data(ctx: DashboardContext, item: ActionItem) -> None:
    src_key = str(item.payload.get("source_key") or item.key.replace("stale_", ""))
    src = next((s for s in ctx.source_status if s.key == src_key), None)
    _section("상황", item.detail)
    if src:
        days = None
        if src.as_of and src.recommended_days is not None:
            days = (ctx.as_of - src.as_of).days
        _section(
            "근거",
            f"- 소스: **{src.label}**\n"
            f"- as_of: `{src.as_of}`\n"
            f"- 권장 주기: {src.recommended_days}일\n"
            f"- 경과일: **{days if days is not None else '—'}일**\n"
            f"- 경로: `{src.path}`",
        )
    else:
        _section("근거", item.detail)

    st.markdown("**[처리]**")
    st.caption("PC에서 실행됩니다. 폰에서는 결과만 확인하세요.")
    if st.button("지금 갱신", type="primary", key=f"data_run_{src_key}"):
        with st.spinner("갱신 중…"):
            result = run_data_refresh(ctx.data_dir, scope="holdings")
        journal_data_refresh(
            as_of=date.today(),
            ok=result.ok,
            message=result.message,
            detail=result.detail,
        )
        if result.ok:
            ctx.runtime.touch_refresh("prices_fundamentals")
            ctx.runtime.save(ctx.root / "data" / "alpha_dashboard_runtime.json")
            st.success(result.message)
            st.session_state.pop(SESSION_PANEL, None)
            st.rerun()
        else:
            st.error(result.message)

    if st.button("전체 화면에서 보기 (데이터 갱신)", key=f"data_full_{src_key}"):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_EVENTS, focus=FOCUS_DATA_REFRESH)


def _panel_rescore(ctx: DashboardContext, item: ActionItem) -> None:
    """Human CECS re-review only — never auto-changes scores."""
    triggers = item.payload.get("triggers") or []
    tickers = item.payload.get("tickers") or []
    _section("상황", item.detail)
    _section(
        "근거",
        "- 트리거: "
        + (", ".join(f"`{t}`" for t in triggers) if triggers else "—")
        + "\n- 종목: "
        + (", ".join(f"`{t}`" for t in tickers) if tickers else "관련 종목")
        + "\n- **CECS·total_score는 자동 변경되지 않습니다.**",
    )
    st.markdown("**[처리]**")
    st.caption("결재함에서 출처 확인 후 CECS를 사람이 재채점하세요.")
    if st.button("결재함으로 이동", type="primary", key="rescore_to_approval"):
        from alpha_system.scoring.pending_rescore import dismiss_pending, pending_path

        key = str(item.key or "")
        if key:
            dismiss_pending(key, path=pending_path(ctx.root))
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)


def _panel_swap(ctx: DashboardContext, item: ActionItem) -> None:
    held = str(item.payload.get("held") or "")
    cand = str(item.payload.get("candidate") or "")
    gap = item.payload.get("gap_pct")
    hits = item.payload.get("hits")
    held_score = item.payload.get("held_score")
    cand_score = item.payload.get("cand_score")
    _section("상황", item.detail)
    _section(
        "근거",
        f"- 보유 최하위: `{held}` score={held_score}\n"
        f"- 후보: `{cand}` score={cand_score}\n"
        f"- gap: **{gap}%** / consecutive hits: **{hits}**\n"
        f"- 모드: `{ctx.cfg.swap_rule.mode}`",
    )
    st.markdown("**[처리]**")
    st.info(copy_get("action_panel", "swap_observe_only"))
    if st.button("전체 화면에서 보기 (포트폴리오)", key="swap_full"):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_PORTFOLIO)


def _aux_link_generic(ctx: DashboardContext, item: ActionItem) -> None:
    if st.button("전체 화면에서 보기", key=f"gen_full_{item.key}"):
        st.session_state.pop(SESSION_PANEL, None)
        navigate(PAGE_RULES)


def _kr_alpha_sleeve_value(ctx: DashboardContext) -> Optional[float]:
    path = ctx.data_dir / "positions.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty or "asset_group" not in df.columns:
        return None
    kr = df[df["asset_group"] == "kr_alpha"]
    if kr.empty or "current_value" not in kr.columns:
        return None
    return float(pd.to_numeric(kr["current_value"], errors="coerce").fillna(0).sum())


def _total_portfolio_value(ctx: DashboardContext) -> Optional[float]:
    path = ctx.data_dir / "positions.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty or "current_value" not in df.columns:
        return None
    total = float(pd.to_numeric(df["current_value"], errors="coerce").fillna(0).sum())
    return total if total > 0 else None


def _alpha_book_krw(ctx: DashboardContext) -> tuple[Optional[float], str]:
    """Alpha book size in KRW for tranche sizing display."""
    capital_frac = float(ctx.cfg.capital.max_fraction_of_total_assets)
    total = _total_portfolio_value(ctx)
    if total is not None:
        return total * capital_frac, f"총자산×{capital_frac * 100:.0f}%"
    sleeve = _kr_alpha_sleeve_value(ctx)
    if sleeve is not None and sleeve > 0:
        return sleeve, "kr_alpha 평가액(폴백)"
    return None, "positions.csv 평가액 없음"


def _eligible_tickers(ctx: DashboardContext) -> list[str]:
    out: list[str] = []
    for s in ctx.scoreboard_rows:
        if s.eligibility is True:
            out.append(s.ticker)
        elif s.eligibility is None and s.total_score is not None:
            out.append(s.ticker)
    ops = getattr(ctx, "ops_portfolio_rows", None) or ctx.portfolio_rows
    held = {r.ticker for r in ops}
    out = sorted(out, key=lambda t: (0 if t in held else 1, t))
    return out[:12]


def _sizing_excerpt(
    ctx: DashboardContext,
    tid: str,
    *,
    tranche_krw: Optional[float] = None,
) -> tuple[str, Optional[str], list[dict]]:
    """Return (markdown evidence, block message, suggested fills)."""
    suggested: list[dict] = []
    _, init_cap, mkt_cap = (
        int(ctx.cfg.sizing.target_names),
        float(ctx.cfg.sizing.initial_weight_cap),
        float(ctx.cfg.sizing.market_value_cap),
    )
    del init_cap  # reserved for future initial-cap headroom display
    ops = getattr(ctx, "ops_portfolio_rows", None) or ctx.portfolio_rows
    # held sum vs per-name market_value_cap headroom (ops_book only)
    held_sum = sum(r.weight_pct for r in ops)
    name_caps = []
    for r in ops:
        headroom = max(0.0, mkt_cap * 100.0 - r.weight_pct)
        name_caps.append((r.ticker, headroom))
    min_headroom = min((h for _, h in name_caps), default=mkt_cap * 100.0)

    headroom_lines = (
        f"- 보유 합산 비중: **{held_sum:.1f}%**\n"
        f"- 종목 cap ({mkt_cap * 100:.0f}%): 최소 여유 **{min_headroom:.1f}%p**"
    )
    if name_caps:
        tight = sorted(name_caps, key=lambda x: x[1])[:3]
        headroom_lines += " · 여유 부족: " + ", ".join(
            f"`{t}` {h:.1f}%p" for t, h in tight if h < 10
        )
    headroom_lines += "\n"

    if ctx.cfg.scoring.score_cutoff is None:
        lines = (
            headroom_lines
            + "- eligibility: **score_cutoff 미확정** — 정식 배분안 산출 불가\n"
            + "- 보유·스코어보드 참고 종목만 표시합니다.\n"
        )
        for t in _eligible_tickers(ctx)[:6]:
            sc = next((s for s in ctx.scoreboard_rows if s.ticker == t), None)
            lines += (
                f"  - `{t}` total={sc.total_score if sc else '—'} "
                f"elig={sc.eligibility if sc else '—'}\n"
            )
            suggested.append({"ticker": t, "incr_pct": 0.0, "krw": None})
        return (
            lines,
            "score_cutoff 미확정으로 자동 배분안을 확정할 수 없습니다. "
            "기록은 수동 체결 기준으로만 가능합니다.",
            suggested,
        )

    scores: list[NameScore] = []
    for s in ctx.scoreboard_rows:
        try:
            ns = score_name(
                ticker=s.ticker,
                name=s.name,
                score_q=s.score_q,
                score_v=s.score_v,
                score_sr=s.score_sr,
                score_r=s.score_r,
                cecs=s.cecs,
                system_cfg=ctx.cfg,
            )
            ns.sector = str(getattr(s, "sector", "") or "")
            scores.append(ns)
        except Exception:
            continue
    existing = {r.ticker: r.weight_pct / 100.0 for r in ops}
    try:
        result = allocate_tranche(
            ctx.cfg,
            tranche_id=TrancheId(tid),
            scores=scores,
            existing_weights=existing,
        )
    except Exception as exc:
        return headroom_lines + f"- sizing 오류: {exc}\n", str(exc), []

    target_ok = _exit_target_tickers(ctx)
    require_tv = bool(ctx.cfg.exit.entry_require_target_valuation)

    lines = (
        headroom_lines
        + f"- 적격 종목 수: **{result.eligible_count}** / target {result.target_names}\n"
        + f"- 트랜치 예산: **{result.tranche_budget * 100:.1f}%p**"
    )
    if tranche_krw is not None:
        lines += f" (약 **{tranche_krw:,.0f}원**)\n"
    else:
        lines += "\n"
    lines += "- 배분안 (이번 트랜치 증분 · 종목·금액):\n"
    if not result.allocated:
        lines += "  - (배분 없음)\n"
    waiting_lines: list[str] = []
    for a in result.allocated:
        if a.incremental_weight <= 0:
            continue
        tk = str(a.ticker).zfill(6)
        if require_tv and tk not in target_ok:
            waiting_lines.append(
                f"  - `{a.ticker}` 대기 후보 — 목표가 미승인 · 편입 차단 "
                f"(증분 {a.incremental_weight * 100:.2f}%p는 참고만)\n"
            )
            continue
        krw = (
            tranche_krw * (a.incremental_weight / result.tranche_budget)
            if tranche_krw is not None and result.tranche_budget > 0
            else None
        )
        if krw is None and tranche_krw is None:
            krw_s = "금액 환산 불가"
        elif krw is None:
            krw_s = "—"
        else:
            krw_s = f"약 {krw:,.0f}원"
        lines += (
            f"  - `{a.ticker}` +{a.incremental_weight * 100:.2f}%p · **{krw_s}** "
            f"(누적 {a.total_weight_after * 100:.2f}%{' · capped' if a.capped else ''})\n"
        )
        suggested.append(
            {
                "ticker": a.ticker,
                "incr_pct": a.incremental_weight * 100.0,
                "krw": krw,
            }
        )
    if waiting_lines:
        lines += "- 대기 후보 (목표가 다음 주 E까지 · 체결 제외):\n"
        lines += "".join(waiting_lines)
        blocked_note = (
            "목표가 미승인 대기 후보는 배분 참고만 표시하며 체결 입력에서 제외합니다."
        )
    else:
        blocked_note = None

    if result.unallocated_weight > 1e-9:
        lines += f"- 미배분: **{result.unallocated_weight * 100:.2f}%p**\n"
    for w in result.warnings:
        lines += f"- ⚠ {w}\n"

    return lines, blocked_note, suggested
