"""Proposal Shadow backtest page — 수급 브리핑형 KPI·곡선·이벤트 (Review-only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from alpha_system.ui.services.approval_chrome import page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.proposal_backtest_board import (
    build_proposal_backtest_board,
    format_ticker_label,
    kpi_html,
    load_ticker_name_map,
    trades_table_dicts,
)
from alpha_system.ui.services.ui_copy import copy_get


def render_backtest(ctx: DashboardContext) -> None:
    page_head(
        kicker=copy_get("backtest", "page_kicker", default="백테스트"),
        title=copy_get(
            "backtest",
            "page_title",
            default="제안 종목 Shadow",
        ),
        lead=copy_get(
            "backtest",
            "page_lead",
            default=(
                "중기 제안 규칙으로 가상 체결한 Net 곡선입니다. "
                "주차별 제안 × 주가 재현 또는 일별 Shadow · "
                "target·자동주문 없음 · Review-only."
            ),
        ),
    )

    market = str(getattr(ctx, "screen_market", None) or "KOSPI").upper()
    st.caption(
        copy_get(
            "backtest",
            "market_caption",
            default="시장={m} · 중기 Shadow · 단기·수급 선정 로직 아님",
            m=market,
        )
    )
    try:
        from alpha_system.shadow.strategy_parity import (
            build_strategy_parity_board,
            strategy_parity_html,
        )

        _bt_parity = build_strategy_parity_board(Path(ctx.root))
        st.markdown(strategy_parity_html(_bt_parity), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "backtest",
                "parity_caption",
                default=(
                    "패리티: mid_lab_weekly KPI = Soft `{lab}` 가상 성과 · "
                    "실구성 정본=포트 중기 ③제안 · 이평 Soft {ma} · "
                    "보유는 제안에 맞출 것 · target 자동 없음 · STRATEGY_PARITY_SPEC"
                ),
                lab=_bt_parity.engine_label,
                ma=("on" if _bt_parity.apply_ma_soft else "off"),
            )
        )
    except Exception:  # noqa: BLE001
        pass

    src_key = f"bt_source_{market}"
    if src_key not in st.session_state:
        st.session_state[src_key] = "replay"
    meta_key = f"bt_replay_meta_{market}"

    mode_key = f"bt_replay_mode_{market}"
    replay_mode = st.radio(
        copy_get("backtest", "mode_label", default="재현 방식"),
        options=["mid_lab_weekly", "short_lab_weekly", "pit_soft_l3", "freeze"],
        format_func=lambda x: {
            "mid_lab_weekly": copy_get(
                "backtest",
                "mode_mid_lab",
                default="중기 Lab · 주간 리밸 · 60/180일 표본",
            ),
            "short_lab_weekly": copy_get(
                "backtest",
                "mode_short_lab",
                default="단기 수익기 · 60/120·score_m · 60/180일",
            ),
            "pit_soft_l3": copy_get(
                "backtest",
                "mode_pit",
                default="실 mid 스냅 PIT (짧으면 참고만)",
            ),
            "freeze": copy_get(
                "backtest",
                "mode_freeze",
                default="사후고정 창 (참고)",
            ),
        }.get(x, x),
        horizontal=True,
        key=mode_key,
        index=0,
    )
    period_key = f"bt_lookback_{market}"
    lookback_label = st.radio(
        copy_get("backtest", "period_label", default="유의미 기간"),
        options=["60", "180", "252", "350"],
        format_func=lambda x: {
            "60": copy_get("backtest", "period_60", default="60거래일 · 예비"),
            "180": copy_get(
                "backtest", "period_180", default="180거래일 · 잠정(Go-live)"
            ),
            "252": copy_get(
                "backtest", "period_252", default="252거래일 · 전략(≈1년)"
            ),
            "350": copy_get(
                "backtest",
                "period_350",
                default="350거래일 · 전략(가용 최대에 가깝게)",
            ),
        }.get(x, x),
        horizontal=True,
        key=period_key,
        index=2,
    )
    lookback = int(lookback_label)
    pit = replay_mode == "pit_soft_l3"
    mid_lab = replay_mode == "mid_lab_weekly"
    short_lab = replay_mode == "short_lab_weekly"

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        replay = st.button(
            copy_get(
                "backtest",
                "btn_replay",
                default="가격 보강 후 재현",
            ),
            key=f"bt_price_replay_{market}",
            type="primary",
        )
    with col_b:
        run = st.button(
            copy_get("backtest", "btn_rerun", default="오늘 Shadow 다시 계산"),
            key=f"bt_shadow_rerun_{market}",
        )
    with col_c:
        hint_key = (
            "replay_hint_short_lab"
            if short_lab
            else (
                "replay_hint_mid_lab"
                if mid_lab
                else ("replay_hint_pit" if pit else "replay_hint")
            )
        )
        st.caption(
            copy_get(
                "backtest",
                hint_key,
                default=(
                    "단기=주간 60∧120∧score_m · 120이탈 제외 · 중기 QVM 비혼합 · "
                    "score_m 최신 고정(PIT 없음) · target·자동주문 없음"
                    if short_lab
                    else (
                        "중기=주간 리밸·Soft/이평은 스냅일에만 · 60예비/180잠정 표본 · "
                        "12일 PIT 대체 · target·자동주문 없음"
                        if mid_lab
                        else (
                            "실 mid 스냅 PIT · 짧으면 참고만(Go-live 판정 금지) · target 불변"
                            if pit
                            else (
                                "기간=표본 품질과 동일(60예비/180잠정) · "
                                "pykrx 보강 후 재현 · target 불변"
                            )
                        )
                    )
                ),
            )
        )

    if replay:
        try:
            from alpha_system.shadow.proposal_price_replay import (
                LOOKBACK_PRELIMINARY,
                run_proposal_price_replay,
            )

            with st.spinner(
                copy_get(
                    "backtest",
                    "replay_spinner",
                    default="가격 보강 후 {n}거래일 재현 중…",
                    n=lookback,
                )
            ):
                weeks = None
                selection_prefix = ""
                skip_run = False
                lab_mode = mid_lab or short_lab
                if mid_lab:
                    from alpha_system.shadow.profit_lab import (
                        build_sufficient_mid_weeks,
                    )

                    weeks, lab_meta = build_sufficient_mid_weeks(
                        Path(ctx.root),
                        lookback_trading_days=lookback,
                        ensure_prices=True,
                    )
                    if not weeks:
                        st.warning(
                            copy_get(
                                "backtest",
                                "replay_fail",
                                default="재현 불가 · {r}",
                                r=str(lab_meta.get("reason") or "lab_weeks_empty"),
                            )
                        )
                        skip_run = True
                    else:
                        selection_prefix = (
                            f"중기 Lab 주간리밸 · 주 {lab_meta.get('n_weeks')} · "
                            f"{lab_meta.get('params_label')} · "
                        )
                elif short_lab:
                    from alpha_system.shadow.short_profit_lab import (
                        build_sufficient_short_weeks,
                    )

                    weeks, lab_meta = build_sufficient_short_weeks(
                        Path(ctx.root),
                        lookback_trading_days=lookback,
                        ensure_prices=True,
                    )
                    if not weeks:
                        st.warning(
                            copy_get(
                                "backtest",
                                "replay_fail",
                                default="재현 불가 · {r}",
                                r=str(lab_meta.get("reason") or "short_lab_empty"),
                            )
                        )
                        skip_run = True
                    else:
                        selection_prefix = (
                            f"단기 Lab 60/120·score_m · 주 {lab_meta.get('n_weeks')} · "
                            f"{lab_meta.get('params_label')} · "
                        )
                if skip_run:
                    result = None
                else:
                    result = run_proposal_price_replay(
                        Path(ctx.root),
                        market=market,
                        persist=True,
                        weeks=weeks,
                        lookback_trading_days=lookback,
                        min_trading_days=lookback,
                        ensure_prices=not lab_mode,
                        allow_short=False,
                        point_in_time=True if (pit or lab_mode) else False,
                        apply_l3=True if (pit or mid_lab) else False,
                        apply_soft=False if lab_mode else pit,
                        # Lab 주간 스냅에 Soft·이평·틸트 이미 반영 → 재필터 금지(난매·과필터)
                        apply_soft_cut=not lab_mode,
                        apply_ma_soft=not lab_mode,
                        ma_mode="above_60",
                        mid_cadence=True,
                        add_frac=0.25,
                        soft_hold_r1=None if lab_mode else -0.08,
                        mkt_5d_cash=None if lab_mode else -0.025,
                        risk_on_20d=None if lab_mode else (0.0 if pit else None),
                        horizon="short" if short_lab else "mid",
                    )
                    if (
                        lab_mode
                        and result.ok
                        and result.n_days < LOOKBACK_PRELIMINARY
                    ):
                        st.warning(
                            copy_get(
                                "backtest",
                                "sample_too_short_mid",
                                default=(
                                    "표본 {n}일 < 예비 {m}일 · "
                                    "가격·주간 스냅을 더 쌓은 뒤 Go-live 판정"
                                ),
                                n=result.n_days,
                                m=LOOKBACK_PRELIMINARY,
                            )
                        )
            if result is not None and result.ok:
                note = (selection_prefix or "") + (result.selection_note or "")
                st.session_state[src_key] = "replay"
                st.session_state[meta_key] = {
                    "n_weeks": result.n_weeks,
                    "missing_price_names": result.missing_price_names,
                    "lookback": result.lookback_trading_days,
                    "selection_note": note,
                    "horizon": "short" if short_lab else "mid",
                    "replay_mode": replay_mode,
                }
                st.success(
                    copy_get(
                        "backtest",
                        "replay_ok",
                        default=(
                            "재현 완료 · {d0}→{d1} · {n}일(목표 {lb}) · "
                            "제안 {w}주 · 보강+{a}행 · 결측 {m}종"
                        ),
                        d0=result.as_of_first or "—",
                        d1=result.as_of_last or "—",
                        n=result.n_days,
                        lb=result.lookback_trading_days,
                        w=result.n_weeks,
                        a=result.backfill_rows_added,
                        m=result.missing_price_names,
                    )
                )
                if note:
                    st.caption(note)
            elif result is not None:
                st.warning(
                    copy_get(
                        "backtest",
                        "replay_fail",
                        default="재현 불가 · {r}",
                        r=result.reason or "unknown",
                    )
                )
                if result.selection_note:
                    st.caption(result.selection_note)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"주가 재현 실패 · {exc}")

    if run:
        try:
            from alpha_system.shadow.run import run_shadow_day

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
            result = run_shadow_day(
                Path(ctx.root),
                market=market,
                proposal_rows=list(getattr(ctx, "portfolio_rows", None) or [])
                + cov_extra,
                ops_rows=list(getattr(ctx, "ops_portfolio_rows", None) or []),
                persist=True,
            )
            def _l3_after_shadow() -> str:
                try:
                    from alpha_system.ui.services.refresh import (
                        persist_l3_review_after_shadow,
                    )

                    l3_out = persist_l3_review_after_shadow(
                        Path(ctx.root), market=market
                    )
                    l3_ok = (l3_out.get("l3") or {}).get("ok")
                    fear_ok = (l3_out.get("fear_soft") or {}).get("ok")
                    if l3_ok or fear_ok:
                        return copy_get(
                            "backtest",
                            "l3_bundle_ok",
                            default=" · L3·Fear Soft 이력도 갱신",
                        )
                    if (l3_out.get("l3") or {}).get("error"):
                        return " · L3 이력 건너뜀"
                except Exception:  # noqa: BLE001
                    return " · L3 이력 건너뜀"
                return ""

            if result.get("skipped"):
                st.info(
                    copy_get(
                        "backtest",
                        "skip_msg",
                        default="이미 기록된 일자입니다 · as_of={d}",
                        d=result.get("as_of") or "—",
                    )
                    + _l3_after_shadow()
                )
            elif result.get("ok"):
                st.session_state[src_key] = "live"
                st.success(
                    copy_get(
                        "backtest",
                        "ok_msg",
                        default="Shadow 일자를 기록했습니다 · as_of={d}",
                        d=result.get("as_of") or "—",
                    )
                    + _l3_after_shadow()
                )
            else:
                st.warning(
                    copy_get(
                        "backtest",
                        "fail_msg",
                        default="계산 불가 · {r}",
                        r=result.get("reason") or "unknown",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Shadow 재계산 실패 · {exc}")

    source = st.radio(
        copy_get("backtest", "source_label", default="표시 원장"),
        options=["replay", "live"],
        format_func=lambda x: (
            copy_get("backtest", "source_replay", default="주가 재현")
            if x == "replay"
            else copy_get("backtest", "source_live", default="일별 Shadow")
        ),
        horizontal=True,
        key=src_key,
    )

    meta = st.session_state.get(meta_key) or {}
    board_horizon = str(meta.get("horizon") or ("short" if short_lab else "mid"))
    board = build_proposal_backtest_board(
        Path(ctx.root),
        market=market,
        source=str(source),
        n_weeks=int(meta.get("n_weeks") or 0),
        missing_price_names=int(meta.get("missing_price_names") or 0),
        horizon=board_horizon,
    )
    name_map = load_ticker_name_map(
        Path(ctx.root),
        market=market,
        extra_rows=list(getattr(ctx, "portfolio_rows", None) or [])
        + list(getattr(ctx, "ops_portfolio_rows", None) or [])
        + list(getattr(ctx, "scoreboard_rows", None) or []),
    )
    st.markdown(kpi_html(board), unsafe_allow_html=True)

    st.markdown(
        f"### {copy_get('backtest', 'sec_curve', default='자산 곡선')}"
    )
    if board.equity:
        curve = pd.DataFrame(
            [
                {"date": e["date"], "NAV(Net)": float(e["equity"])}
                for e in board.equity
                if e.get("date")
            ]
        )
        if not curve.empty:
            curve = curve.set_index("date")
            st.line_chart(curve, height=260)
        else:
            st.caption(
                copy_get(
                    "backtest",
                    "curve_empty",
                    default="곡선 데이터가 없습니다.",
                )
            )
    else:
        empty_key = "empty_replay" if source == "replay" else "empty"
        st.info(
            copy_get(
                "backtest",
                empty_key,
                default=(
                    "주가 재현 기록이 없습니다. 「주가 재현 돌리기」를 누르세요."
                    if source == "replay"
                    else (
                        "Shadow 기록이 없습니다. 포트폴리오를 연 뒤 "
                        "「오늘 Shadow 다시 계산」을 누르거나, "
                        "가격·제안이 있는 날 대시보드를 열어 누적하세요."
                    )
                ),
            )
        )

    st.markdown(
        f"### {copy_get('backtest', 'sec_trades', default='리밸·매매 이벤트')}"
    )
    st.caption(
        copy_get(
            "backtest",
            "trades_caption",
            default=(
                "일별 비중 변경 이벤트 (편입·청산·추가 등) · "
                "수급 브리핑의 종료 매매 표에 대응 · Review-only"
            ),
        )
    )
    trade_rows = trades_table_dicts(board, names=name_map)
    if trade_rows:
        st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
    else:
        st.caption(
            copy_get(
                "backtest",
                "trades_empty",
                default="이벤트 없음 · 보유 드리프트만 있거나 표본이 짧습니다.",
            )
        )

    if source == "replay" and board.n_days > 0:
        st.markdown(
            f"### {copy_get('backtest', 'sec_names', default='종목별 진단')}"
        )
        st.caption(
            copy_get(
                "backtest",
                "names_caption",
                default=(
                    "누가 끌어내렸는지 보는 진단용 · "
                    "포트 의사결정 대체가 아님 · Review-only"
                ),
            )
        )
        try:
            from alpha_system.shadow.mid_ledger import load_ledger
            from alpha_system.shadow.proposal_price_replay import (
                _read_prices_history,
                name_stats_from_ledger,
                prices_history_path,
                proposal_replay_prices_path,
            )

            from alpha_system.proposal_chart import norm_ticker

            led_rows = load_ledger(Path(board.ledger))
            tickers = sorted(
                {
                    norm_ticker(k)
                    for r in led_rows
                    for k, w in (r.get("weights") or {}).items()
                    if float(w or 0) > 1e-8
                }
            )
            px = _read_prices_history(
                proposal_replay_prices_path(Path(ctx.root)),
                tickers,
                extra_paths=[
                    prices_history_path(Path(ctx.root)),
                    Path(ctx.root) / "data" / "prices.csv",
                ],
            )
            stats = name_stats_from_ledger(led_rows, px=px if not px.empty else None)
            if stats:
                soft_tk: list[str] = []
                try:
                    soft_tk = [
                        norm_ticker(getattr(r, "ticker", None))
                        for r in (ctx.portfolio_rows or [])
                        if norm_ticker(getattr(r, "ticker", None))
                    ]
                except Exception:  # noqa: BLE001
                    soft_tk = []
                from alpha_system.ui.services.bt_name_inference import (
                    bt_name_inference_html,
                    build_bt_name_inference_board,
                )

                infer = build_bt_name_inference_board(
                    Path(ctx.root),
                    stats,
                    market=str(
                        getattr(ctx, "screen_market", None)
                        or getattr(ctx, "market", None)
                        or "KOSPI"
                    ),
                    soft_tickers=soft_tk,
                    name_by=name_map,
                    top_n=5,
                )
                st.markdown(bt_name_inference_html(infer), unsafe_allow_html=True)
                st.caption(
                    copy_get(
                        "backtest",
                        "names_infer_caption",
                        default=(
                            "상위/하위 공통 피처 → Soft·논리가치 규칙 가설 · "
                            "승자 티커 매수 신호 아님 · Review-only"
                        ),
                    )
                )
                show = []
                for s in stats:
                    pr = s.get("price_ret")
                    tk = str(s.get("ticker") or "")
                    show.append(
                        {
                            "종목": format_ticker_label(tk, name_map),
                            "티커": norm_ticker(tk),
                            "보유일": s.get("days_held"),
                            "부터": s.get("from"),
                            "까지": s.get("to"),
                            "가격수익률": (
                                None if pr is None else f"{100.0 * float(pr):+.1f}%"
                            ),
                        }
                    )
                with st.expander("종목 전체 표", expanded=False):
                    st.dataframe(
                        pd.DataFrame(show),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.caption("종목 통계 없음")
        except Exception as exc:  # noqa: BLE001
            st.caption(f"종목 진단 생략 · {exc}")

    with st.expander(
        copy_get("backtest", "sec_more", default="원장 · Go-live 참고"),
        expanded=False,
    ):
        st.caption(f"ledger · `{board.ledger}`")
        st.caption(
            copy_get(
                "backtest",
                "golive_note",
                default=(
                    "Go-live 게이트는 docs/SHADOW_MID_PROFIT_MACHINE.md · "
                    "시스템이 target을 쓰지 않습니다. 통과 판정은 사람."
                ),
            )
        )
        if board.attribution:
            bits = [
                f"{k} {v:+.4f}"
                for k, v in board.attribution.items()
                if abs(float(v or 0)) > 1e-8
            ]
            st.caption("attribution · " + (" · ".join(bits) if bits else "—"))

    _render_household_alloc_lab(Path(ctx.root))


def _render_household_alloc_lab(root: Path) -> None:
    """가계 본체 Lab · 정적 차용 + 듀얼모멘텀 · Soft/target 불변."""
    with st.expander(
        copy_get(
            "backtest",
            "household_lab_fold",
            default="가계 본체 Lab · 정적·동적 비교 (국내 ETF)",
        ),
        expanded=False,
    ):
        st.caption(
            copy_get(
                "backtest",
                "household_lab_caption",
                default=(
                    "A안 Review-only · 올웨더·영구·60/40·한국형·듀얼모멘텀 근사 · "
                    "알파 Soft 교체 아님 · target 불변"
                ),
            )
        )
        st.caption(
            copy_get(
                "backtest",
                "household_lab_auto_hint",
                default="일상=확인① · 여기는 Soft Shadow 본진 · Lab 강제는 선택",
            )
        )
        if st.button(
            copy_get(
                "backtest",
                "household_lab_btn",
                default="가계 Lab 강제 재계산",
            ),
            key="btn_household_alloc_lab",
            type="secondary",
            use_container_width=True,
        ):
            try:
                from alpha_system.shadow.household_alloc_lab import (
                    run_household_alloc_lab,
                    save_report,
                )

                with st.spinner(
                    copy_get(
                        "backtest",
                        "household_lab_spinner",
                        default="국내 ETF 가격·정적/동적 Lab 계산 중…",
                    )
                ):
                    report = run_household_alloc_lab(root, ensure_fetch=True)
                    save_report(root, report)
                if report.ok:
                    st.success(
                        copy_get(
                            "backtest",
                            "household_lab_ok",
                            default="가계 Lab 완료 · 성공 {n} · Soft·target 불변",
                            n=sum(1 for s in report.strategies if s.ok),
                        )
                    )
                else:
                    st.warning(
                        copy_get(
                            "backtest",
                            "household_lab_fail",
                            default="가계 Lab 일부/전체 실패 · 리포트 확인",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                st.warning(f"가계 Lab 실패 · {exc}")
        try:
            from alpha_system.shadow.household_alloc_lab import (
                household_alloc_table_html,
                load_report,
                run_household_alloc_lab,
            )

            cached = load_report(root)
            if cached:
                st.markdown(
                    household_alloc_table_html(cached),
                    unsafe_allow_html=True,
                )
            else:
                st.caption(
                    copy_get(
                        "backtest",
                        "household_lab_empty",
                        default="아직 리포트 없음 · 「가계 Lab 재계산」을 누르세요.",
                    )
                )
                # dry validate recipes without network
                _ = run_household_alloc_lab
            try:
                from alpha_system.ui.services.corr_review_board import (
                    build_and_render_corr_review,
                )

                st.caption(
                    copy_get(
                        "backtest",
                        "corr_review_caption",
                        default=(
                            "상관 Review · 정적·나침반 레그 · "
                            "제안비중 표시만 · Soft·target 불변"
                        ),
                    )
                )
                _b, _h = build_and_render_corr_review(root, ensure_fetch=False)
                st.markdown(_h, unsafe_allow_html=True)
            except Exception:  # noqa: BLE001
                pass
            _render_household_regime_lab(root)
            _render_us_gem_regime_lab(root)
            _render_long_gem_regime_lab(root)
        except Exception as exc:  # noqa: BLE001
            st.caption(f"가계 Lab 표시 생략 · {exc}")


def _render_long_gem_regime_lab(root: Path) -> None:
    """Ken French 월간 · 대공황~ 장기 GEM 검증."""
    st.caption(
        copy_get(
            "backtest",
            "long_gem_regime_caption",
            default=(
                "장기 월간(1926~): Ken French · 대공황=절대모멘텀 · "
                "상대 GEM은 1990~ · Review-only"
            ),
        )
    )
    if st.button(
        copy_get(
            "backtest",
            "long_gem_regime_btn",
            default="장기 월간 GEM(대공황~) 재계산",
        ),
        key="btn_long_gem_regime_lab",
        type="secondary",
        use_container_width=True,
    ):
        try:
            from alpha_system.shadow.long_gem_regime_lab import (
                run_long_gem_regime_lab,
                save_report as save_long_gem_report,
            )

            with st.spinner(
                copy_get(
                    "backtest",
                    "long_gem_regime_spinner",
                    default="Ken French 월간 · 대공황~ 국면 슬라이스 중…",
                )
            ):
                lrep = run_long_gem_regime_lab(root, ensure_fetch=True)
                save_long_gem_report(root, lrep)
            if lrep.ok:
                st.success(
                    copy_get(
                        "backtest",
                        "long_gem_regime_ok",
                        default="장기 GEM Lab 완료 · Soft·target 불변",
                    )
                )
            else:
                st.warning(
                    copy_get(
                        "backtest",
                        "long_gem_regime_fail",
                        default="장기 GEM Lab 실패 · FF 다운로드 확인",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"장기 GEM Lab 실패 · {exc}")
    try:
        from alpha_system.shadow.long_gem_regime_lab import (
            load_report as load_long_gem_report,
            long_gem_table_html,
        )

        cached_l = load_long_gem_report(root)
        if cached_l:
            st.markdown(
                long_gem_table_html(cached_l),
                unsafe_allow_html=True,
            )
        else:
            st.caption(
                copy_get(
                    "backtest",
                    "long_gem_regime_empty",
                    default="장기 리포트 없음 · 「장기 월간 GEM(대공황~) 재계산」",
                )
            )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"장기 GEM Lab 표시 생략 · {exc}")


def _render_us_gem_regime_lab(root: Path) -> None:
    """미국 ETF GEM 국면 검증 · Soft/target 불변."""
    st.caption(
        copy_get(
            "backtest",
            "us_gem_regime_caption",
            default=(
                "미국 ETF 검증: SPY·EFA/VXUS·BIL·AGG · "
                "국면 정의=국내 Lab과 동일 · Review-only"
            ),
        )
    )
    if st.button(
        copy_get(
            "backtest",
            "us_gem_regime_btn",
            default="미국 ETF GEM 국면 Lab 재계산",
        ),
        key="btn_us_gem_regime_lab",
        type="secondary",
        use_container_width=True,
    ):
        try:
            from alpha_system.shadow.us_gem_regime_lab import (
                run_us_gem_regime_lab,
                save_report as save_us_gem_report,
            )

            with st.spinner(
                copy_get(
                    "backtest",
                    "us_gem_regime_spinner",
                    default="Yahoo 미국 ETF · FRED 국면 슬라이스 중…",
                )
            ):
                urep = run_us_gem_regime_lab(root, ensure_fetch=True)
                save_us_gem_report(root, urep)
            if urep.ok:
                st.success(
                    copy_get(
                        "backtest",
                        "us_gem_regime_ok",
                        default="미국 GEM Lab 완료 · Soft·target 불변",
                    )
                )
            else:
                st.warning(
                    copy_get(
                        "backtest",
                        "us_gem_regime_fail",
                        default="미국 GEM Lab 실패 · 네트워크·캐시 확인",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"미국 GEM Lab 실패 · {exc}")
    try:
        from alpha_system.shadow.us_gem_regime_lab import (
            load_report as load_us_gem_report,
            us_gem_regime_table_html,
        )

        cached_u = load_us_gem_report(root)
        if cached_u:
            st.markdown(
                us_gem_regime_table_html(cached_u),
                unsafe_allow_html=True,
            )
        else:
            st.caption(
                copy_get(
                    "backtest",
                    "us_gem_regime_empty",
                    default="미국 GEM 리포트 없음 · 「미국 ETF GEM 국면 Lab 재계산」",
                )
            )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"미국 GEM Lab 표시 생략 · {exc}")


def _render_household_regime_lab(root: Path) -> None:
    """금리/긴축 국면 슬라이스 · Soft/target 불변."""
    st.caption(
        copy_get(
            "backtest",
            "household_regime_caption",
            default=(
                "고금리 확인: 실질≥1% · 연준≥3% · 2022~ 달력 · "
                "stage≥4 · full/저실질과 비교 · Review-only"
            ),
        )
    )
    if st.button(
        copy_get(
            "backtest",
            "household_regime_btn",
            default="국면 슬라이스 Lab 재계산",
        ),
        key="btn_household_regime_lab",
        type="secondary",
        use_container_width=True,
    ):
        try:
            from alpha_system.shadow.household_regime_lab import (
                run_household_regime_lab,
                save_report as save_regime_report,
            )

            with st.spinner(
                copy_get(
                    "backtest",
                    "household_regime_spinner",
                    default="FRED 금리·stage · 가계 NAV 국면 슬라이스 중…",
                )
            ):
                reg = run_household_regime_lab(root, ensure_fetch=True)
                save_regime_report(root, reg)
            if reg.ok:
                st.success(
                    copy_get(
                        "backtest",
                        "household_regime_ok",
                        default="국면 Lab 완료 · Soft·target 불변",
                    )
                )
            else:
                st.warning(
                    copy_get(
                        "backtest",
                        "household_regime_fail",
                        default="국면 Lab 실패 · FRED키·가격 확인",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"국면 Lab 실패 · {exc}")
    try:
        from alpha_system.shadow.household_regime_lab import (
            household_regime_table_html,
            load_report as load_regime_report,
        )

        cached_r = load_regime_report(root)
        if cached_r:
            st.markdown(
                household_regime_table_html(cached_r),
                unsafe_allow_html=True,
            )
        else:
            st.caption(
                copy_get(
                    "backtest",
                    "household_regime_empty",
                    default="국면 리포트 없음 · 「국면 슬라이스 Lab 재계산」",
                )
            )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"국면 Lab 표시 생략 · {exc}")
