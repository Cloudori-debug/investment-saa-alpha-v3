"""전략 운용 — Soft / 단기 / 정적(묶음) / 듀얼 · Review-only."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import PAGE_PORTFOLIO, navigate
from alpha_system.ui.services.strategy_candidates_board import (
    StrategyCandidatesBundle,
    build_strategy_candidates,
    persist_candidates_after_quant,
    render_candidates_section,
)
from alpha_system.ui.services.strategy_compare_board import (
    build_strategy_compare_board,
    find_card,
)
from alpha_system.ui.services.strategy_ops_catalog import strategy_id_from_page
from alpha_system.ui.services.ui_copy import copy_get


def _kpi_line(card) -> str:
    if card.comparable and card.kpi_ok and card.cagr is not None:
        mdd = card.max_drawdown
        m = "—" if mdd is None else f"{100.0 * float(mdd):.1f}%"
        return f"Lab CAGR {100.0 * float(card.cagr):+.1f}% · MDD {m}"
    if card.kpi_ok and card.total_ret is not None:
        return (
            f"참고 총수익 {100.0 * float(card.total_ret):+.1f}% · "
            f"{card.n_days}일 · ETF와 비교금지"
        )
    return str(card.kpi_note or "Lab 미산출")


def _summary_html(*, kpi: str, cadence: str, do_now: str) -> str:
    e = escape
    return (
        '<div class="pf-strat-sum">'
        f'<div class="pf-strat-sum-kpi">{e(kpi)}</div>'
        f'<div class="pf-strat-sum-meta">{e(cadence)}</div>'
        f'<div class="pf-strat-sum-do"><b>지금</b> {e(do_now)}</div>'
        '<div class="pf-hh-tip">Review-only · 자동주문·target 기입 없음</div>'
        "</div>"
    )


def _compact_cand_df(
    bundle: StrategyCandidatesBundle, *, strategy_id: str
) -> pd.DataFrame:
    rows = []
    for c in bundle.by_strategy.get(strategy_id) or []:
        w = "—" if c.weight_pct is None else f"{float(c.weight_pct):g}%"
        rows.append(
            {
                "역할": c.role or "—",
                "종목": c.name or c.ticker,
                "티커": c.ticker,
                "비중": w,
            }
        )
    return pd.DataFrame(rows)


def _load_mid_short(ctx: DashboardContext, root: Path, market: str):
    mid_rows = list(getattr(ctx, "portfolio_rows", None) or [])
    short_rows: list = []
    try:
        from alpha_system.ui.services.context import load_context

        if str(getattr(ctx, "horizon", "mid")).lower() != "short":
            short_ctx = load_context(root, market=market, horizon="short")
            short_rows = list(getattr(short_ctx, "portfolio_rows", None) or [])
        else:
            short_rows = mid_rows
            mid_ctx = load_context(root, market=market, horizon="mid")
            mid_rows = list(getattr(mid_ctx, "portfolio_rows", None) or [])
    except Exception:  # noqa: BLE001
        pass
    return mid_rows, short_rows


def _run_soft_quant(root: Path, market: str) -> None:
    from alpha_system.ui.services.background_job import (
        job_is_busy,
        start_dashboard_job,
    )

    if job_is_busy(root):
        st.warning("이미 갱신 작업이 실행 중입니다.")
        return
    err = start_dashboard_job(
        root, "quant", collect_scope="liquid", market=market
    )
    if err:
        st.warning(err)
        return
    st.success("정량·후보 갱신 시작 · 사이드바 작업 확인")
    st.rerun()


def _run_etf_lab(root: Path, market: str) -> None:
    try:
        from alpha_system.ui.services.ops_journey_chrome import (
            maybe_refresh_household_lab_after_quant,
        )

        with st.spinner("ETF Lab·후보 갱신 중…"):
            hh = maybe_refresh_household_lab_after_quant(root, force=True)
            persist_candidates_after_quant(root, market=market)
        if hh.get("ok") or hh.get("skipped"):
            st.success("ETF Lab·후보 갱신 완료")
        else:
            st.warning(hh.get("error") or "일부 실패")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"갱신 실패 · {exc}")
    st.rerun()


def _render_soft_page(
    ctx: DashboardContext,
    *,
    sid: str,
    card,
    root: Path,
    market: str,
) -> None:
    cadence = (
        "알파 Soft · 확인① 갱신 · 포트 집행"
        if sid == "mid_soft"
        else "알파 위성 · 확인① 공용 · 중기와 비혼합"
    )
    do_now = (
        "후보 확인 → 포트「오늘 매매」팔·유지·사"
        if sid == "mid_soft"
        else "단기 후보만 포트 단기 접기 · 중기와 섞지 않음"
    )
    st.markdown(
        _summary_html(
            kpi=_kpi_line(card),
            cadence=cadence,
            do_now=do_now,
        ),
        unsafe_allow_html=True,
    )
    mid_rows, short_rows = _load_mid_short(ctx, root, market)
    cands = build_strategy_candidates(
        root, market=market, mid_soft_rows=mid_rows, short_prop_rows=short_rows
    )
    render_candidates_section(cands, strategy_id=sid, title="투자 후보")

    st.markdown("### 실행")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "포트에서 집행",
            type="primary",
            key=f"btn_strat_pf_{sid}",
            use_container_width=True,
        ):
            st.session_state["portfolio_section"] = copy_get(
                "portfolio", "tab_ops", default="오늘 매매"
            )
            navigate(PAGE_PORTFOLIO)
    with c2:
        if st.button(
            "Soft 정량 갱신",
            type="secondary",
            key=f"btn_strat_q_{sid}_{market}",
            use_container_width=True,
        ):
            _run_soft_quant(root, market)
    from alpha_system.ui.services.refresh_progress_ui import render_inline_job_progress

    render_inline_job_progress(root, kind="quant")
    st.caption("일상=확인① · Soft 집행=포트「오늘 매매」")

    with st.expander("규칙 · 설명", expanded=False):
        st.markdown(f"**규칙** · {card.rules}")
        st.markdown(f"**하지 않음** · {card.dont}")
        st.markdown(card.what)


def _render_static_book(ctx: DashboardContext, *, root: Path, market: str) -> None:
    from alpha_system.ui.services.static_book_ops import (
        checklist_static,
        recipe_select_labels,
        recommend_static_recipe,
    )

    labels = recipe_select_labels(root)
    if not labels:
        st.warning("정적 레시피가 없습니다 · household_static_alloc.yaml 확인")
        return
    rec = recommend_static_recipe(root)
    try:
        from alpha_system.ui.services.static_body_pick_board import (
            build_and_render_static_body_pick,
        )

        _board, _pick_html = build_and_render_static_body_pick(
            root, ensure_fetch=False
        )
        st.html(_pick_html)
        _ = _board
    except Exception:  # noqa: BLE001
        pass
    id_by_lab = {lab: sid for sid, lab in labels}
    labs = [lab for _, lab in labels]
    default_lab = next((lab for sid, lab in labels if sid == rec), labs[0])
    key = "static_book_recipe_label"
    if key not in st.session_state or st.session_state.get(key) not in labs:
        st.session_state[key] = default_lab
    choice = st.selectbox(
        "활성 레시피 (최종 추천 기본 · 본체 하나 선택)",
        labs,
        key=key,
    )
    recipe_id = id_by_lab.get(str(choice)) or rec
    board = build_strategy_compare_board(root)
    card = find_card(board, recipe_id)
    kpi = _kpi_line(card) if card else "Lab—"
    if recipe_id == rec:
        kpi = f"추천 · {kpi}"
    st.markdown(
        _summary_html(
            kpi=kpi,
            cadence="가계 본체 · 연 1회 리밸 · 앱 밖 집행",
            do_now="비중표 대조 → 매년 1월만 리밸 · Soft·듀얼과 합산 금지",
        ),
        unsafe_allow_html=True,
    )

    mid_rows, short_rows = _load_mid_short(ctx, root, market)
    cands = build_strategy_candidates(
        root, market=market, mid_soft_rows=mid_rows, short_prop_rows=short_rows
    )
    render_candidates_section(
        cands,
        strategy_id=recipe_id,
        title="투자 후보 (선택 레시피)",
    )

    st.markdown("### 실행")
    if st.button(
        "ETF Lab·후보 갱신",
        type="secondary",
        key="btn_static_book_lab",
        use_container_width=True,
    ):
        _run_etf_lab(root, market)
    st.caption("집행은 증권·연금 · 여기선 레시피·비중 Review만")

    st.markdown("### 월·연 체크")
    for line in checklist_static(recipe_id):
        st.markdown(f"- {line}")

    with st.expander("다른 정적 레시피 Lab 한눈", expanded=False):
        from alpha_system.ui.services.static_book_ops import static_recipe_meta

        rows = []
        for m in static_recipe_meta(root):
            cagr = m.get("cagr")
            mdd = m.get("max_drawdown")
            rows.append(
                {
                    "레시피": m["name_ko"],
                    "CAGR": "—" if cagr is None else f"{100.0 * float(cagr):+.1f}%",
                    "MDD": "—" if mdd is None else f"{100.0 * float(mdd):.1f}%",
                    "추천": "◀" if m["id"] == rec else "",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("순위는 ETF Lab 구간 기준 · Soft와 비교금지")

    if card:
        with st.expander("규칙 · 출처", expanded=False):
            st.markdown(f"**규칙** · {card.rules}")
            st.markdown(f"**출처** · {card.source}")
            st.markdown(card.what)


def _render_dual(ctx: DashboardContext, *, root: Path, market: str) -> None:
    from alpha_system.ui.services.dual_momentum_ops import (
        compute_and_persist,
        compute_dual_momentum_signal,
        dual_signal_to_rows,
    )

    sig = compute_dual_momentum_signal(root, ensure_fetch=False)
    if sig.ok:
        kpi = f"현재픽 · {sig.pick_name} ({sig.pick_ticker}) · {sig.pick_role}"
        do_now = sig.reason_ko
    else:
        kpi = sig.error or "시그널 미산출"
        do_now = "아래「시그널·Lab 갱신」후 다시 확인"
    st.markdown(
        _summary_html(
            kpi=kpi,
            cadence="본체 · 월말 점검 · 12M 절대+상대 · 전량 1종목",
            do_now=do_now,
        ),
        unsafe_allow_html=True,
    )

    st.markdown("### 12개월 모멘텀 · 현재픽")
    if sig.ok:
        st.dataframe(
            pd.DataFrame(dual_signal_to_rows(sig)),
            use_container_width=True,
            hide_index=True,
        )
        st.info(f"**보유할 ETF** · {sig.pick_name} `{sig.pick_ticker}` · 비중 100%")
    else:
        st.warning(sig.error or "시그널 없음")

    st.markdown("### 월말 운영")
    for line in sig.checklist or [
        "월말: 미국 vs EAFE 상대 승자 → 승자>달러단기? 예=승자 / 아니오=미종합채",
        "픽 불변이면 홀드 · 바뀌면 전량 교체",
    ]:
        st.markdown(f"- {line}")

    st.markdown("### S&P 200일 Soft (듀얼과 별개)")
    from alpha_system.economy_compass.spx_200dma_soft import (
        build_spx_200dma_soft_board,
    )
    from alpha_system.ui.services.economy_compass_board import (
        spx_200dma_soft_panel_html,
    )

    spx200 = build_spx_200dma_soft_board(root)
    st.markdown(spx_200dma_soft_panel_html(spx200), unsafe_allow_html=True)
    st.caption(
        "2027H2~ 이탈 시 미국주식 Soft 축소 Review · "
        "지금=관측 · GEM 12M 시그널을 덮지 않음 · target 불변"
    )

    st.markdown("### 실행")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "시그널·가격 갱신",
            type="primary",
            key="btn_dual_signal_refresh",
            use_container_width=True,
        ):
            with st.spinner("가격·시그널 갱신…"):
                compute_and_persist(root, ensure_fetch=True)
                _run_etf_lab(root, market)
    with c2:
        if st.button(
            "ETF Lab만 갱신",
            type="secondary",
            key="btn_dual_lab_only",
            use_container_width=True,
        ):
            _run_etf_lab(root, market)
    st.caption("집행=증권·연금 전량 교체 · Soft·정적과 합산 금지 · target 자동 없음")

    with st.expander("GEM 규칙 · 대리 ETF · 주의", expanded=False):
        st.markdown(
            """
**규칙 (Antonacci GEM 정석 근사 · 달러축)**  
1. **상대모멘텀**: 미국 vs **EAFE(선진국 ex-US)** 중 12M 승자  
2. **절대모멘텀**: 그 승자 12M > **달러단기채** → 승자 100% · 아니면 **미종합채 100%**  
3. **주기**: 매월 말 점검 · 픽 같으면 **홀드**

**국내상장 대리 (원화 국채·원화단기 ≠ 안전/현금)**  
- 미국 ≈ TIGER 미국S&P500 `360750` (SPY)  
- 비미 ≈ PLUS 선진국MSCI(합성 H) `195970` (EFA · EAFE)  
- 현금 ≈ TIGER 미국달러단기채권액티브 `329750` (BIL)  
- 안전 ≈ KODEX 미국종합채권SRI액티브(H) `437080` (AGG)

**듀얼에 안 넣음**  
- 코스피 Soft · 유로50단독(`195930`) · 배당30(`245350`) · 별도 신흥 슬리브

**주의**  
- ACWI ex-US 단일 ETF 부재 · 합성·(H) · 배당/세금 미반영  
- Soft·정적과 합산 집행 금지 · target 자동 없음
"""
        )
        for c in sig.caveats:
            st.caption(f"· {c}")


def render_strategy_ops(ctx: DashboardContext, *, page: str | None = None) -> None:
    root = Path(ctx.root)
    page_key = str(page or st.session_state.get("alpha_page") or "")
    sid = strategy_id_from_page(page_key)
    if not sid:
        st.warning(copy_get("strategy_ops", "unknown", default="알 수 없는 전략 탭"))
        return

    market = str(getattr(ctx, "screen_market", None) or "KOSPI")

    if sid == "static_book":
        page_head(
            kicker="전략 운용",
            title="정적 배분",
            lead="본체 정적 레시피를 하나로 운영 · Lab으로 고르고 연 1회 리밸",
        )
        _render_static_book(ctx, root=root, market=market)
        return

    if sid == "dual_momentum":
        page_head(
            kicker="전략 운용",
            title="듀얼모멘텀",
            lead="GEM 월 시그널 · 전량 1종목 · 확인①+이 탭으로 가격 갱신",
        )
        _render_dual(ctx, root=root, market=market)
        return

    board = build_strategy_compare_board(root)
    card = find_card(board, sid)
    if card is None:
        st.warning(copy_get("strategy_ops", "missing", default="전략 카드 없음"))
        return
    page_head(
        kicker="전략 운용",
        title=card.label,
        lead="후보 → 포트 집행 · 일상=확인① · target 자동 없음",
    )
    _render_soft_page(ctx, sid=sid, card=card, root=root, market=market)
