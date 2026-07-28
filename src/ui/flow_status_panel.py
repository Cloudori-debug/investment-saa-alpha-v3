from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.alpha_v2_gate import (
    FLOW_UI_POLICY_LINES,
    build_holdings_target_flow_table,
    build_v2_candidate_flow_table,
    compute_dashboard_cards,
    load_freshness_summary,
    load_leaderboard_tables,
    load_streaks_table,
    load_trim_watch_tables,
)
from src.ui.table_display import alpha_list_table_height, show_dataframe_readable


def _apply_filters(
    df: pd.DataFrame,
    *,
    market: str,
    holding: str,
    freshness: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if market != "ALL" and "market" in out.columns:
        out = out[out["market"].astype(str).str.upper() == market]
    if holding == "보유" and "holding_flag" in out.columns:
        out = out[out["holding_flag"].astype(str).str.lower().isin({"true", "1"})]
    elif holding == "타깃" and "target_flag" in out.columns:
        out = out[out["target_flag"].astype(str).str.lower().isin({"true", "1"})]
    elif holding == "비보유" and "holding_flag" in out.columns:
        out = out[~out["holding_flag"].astype(str).str.lower().isin({"true", "1"})]
    if freshness == "fresh" and "flow_data_stale" in out.columns:
        out = out[out["flow_data_stale"].astype(str).str.lower().isin({"false", "0", ""})]
    elif freshness == "stale" and "flow_data_stale" in out.columns:
        out = out[out["flow_data_stale"].astype(str).str.lower().isin({"true", "1"})]
    return out


def _pick_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    present = [c for c in cols if c in df.columns]
    return df[present] if present else df


def render_flow_status_tab(data_dir: Path, output_dir: Path) -> None:
    st.subheader("수급 현황")
    st.caption("알파 후보 검증 레이어 — 수급은 매수 허가가 아닙니다 (review-only watch)")

    for line in FLOW_UI_POLICY_LINES[:3]:
        st.info(line)

    cards = compute_dashboard_cards(output_dir)
    fresh = load_freshness_summary(output_dir)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fresh Flow (watched)", cards.get("fresh_flow_count", 0))
    c2.metric("Stale Flow (watched)", cards.get("stale_flow_count", 0))
    c3.metric("Buy Watch", cards.get("buy_watch_count", 0))
    c4.metric("Trim Watch", cards.get("trim_watch_count", 0))
    if fresh.get("fresh_ratio") is not None:
        st.caption(
            f"fresh/stale ratio (watched universe): {fresh.get('fresh_ratio', 0):.1%} / "
            f"{fresh.get('stale_ratio', 0):.1%} · scope `{fresh.get('coverage_scope', 'watched_universe')}`"
        )
    st.caption("현재 랭킹·카드는 **watched universe** 기준 (보유/타깃/Signal Board/v2 top30).")
    reasons = fresh.get("stale_reason_summary") or {}
    if reasons:
        top_reasons = sorted(reasons.items(), key=lambda x: -x[1])[:5]
        st.markdown("**Stale 원인 Top**")
        for reason, cnt in top_reasons:
            st.text(f"- {reason}: {cnt}")
    failed = fresh.get("pykrx_failed_tickers") or []
    if failed:
        st.warning(f"PyKRX 실패 ticker ({len(failed)}): {', '.join(failed[:12])}{'…' if len(failed) > 12 else ''}")
    if fresh.get("last_successful_flow_refresh"):
        st.caption(f"마지막 flow refresh: {fresh.get('last_successful_flow_refresh')}")
    st.caption(
        f"cache hit/miss: {fresh.get('cache_hit_count', 0)}/{fresh.get('cache_miss_count', 0)}"
    )
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("연기금 매집(3일+)", cards.get("pension_accumulation_candidates", 0))
    c6.metric("연기금 이탈(3일+)", cards.get("pension_distribution_warnings", 0))
    c7.metric("Actual Buy Allowed", cards.get("actual_buy_allowed", 0))
    c8.metric("NO_TRADE", str(cards.get("no_trade", True)))
    if cards.get("actual_consecutive_days"):
        st.caption("✓ actual_consecutive_days=true — 일별 PyKRX 시계열 기반 연속 일수")
    else:
        st.caption("일별 연속 수급 통계는 전체 분석 후 flow_streaks.csv 생성 시 표시됩니다.")

    f1, f2, f3 = st.columns(3)
    market_filter = f1.selectbox("시장", ["ALL", "KOSPI", "KOSDAQ"], key="flow_market_filter")
    holding_filter = f2.selectbox("보유", ["전체", "보유", "타깃", "비보유"], key="flow_holding_filter")
    fresh_filter = f3.selectbox("신선도", ["전체", "fresh", "stale"], key="flow_fresh_filter")
    holding_map = {"전체": "전체", "보유": "보유", "타깃": "타깃", "비보유": "비보유"}
    fresh_map = {"전체": "전체", "fresh": "fresh", "stale": "stale"}

    sub1, sub2, sub3, sub4, sub5, sub6, sub7, sub8 = st.tabs([
        "보유/타깃", "Alpha v2 후보", "연기금 Top", "외국인 Top", "동반매수",
        "연속 수급", "Trim Watch", "Stale",
    ])

    held_cols = [
        "ticker", "name", "holding_flag", "target_flag", "current_weight", "target_weight",
        "action_state", "flow_signal", "pension_net_buy_20d", "foreign_net_buy_20d",
        "pension_flow_to_market_cap", "pension_flow_to_turnover",
        "pension_streak_direction", "pension_streak_days",
        "flow_confidence", "flow_data_stale", "buy_watch", "trim_watch", "review_only",
    ]
    v2_cols = [
        "final_rank", "ticker", "name", "market", "sector", "grade",
        "total_score_v1", "flow_score", "total_score_v2_shadow",
        "pension_net_buy_20d", "foreign_net_buy_20d",
        "pension_foreign_co_buy", "pension_foreign_co_sell",
        "flow_signal_state", "buy_permission", "review_only", "key_reason",
    ]
    lb_cols = [
        "rank", "ticker", "name", "market", "sector", "net_buy_amount",
        "net_buy_to_market_cap", "consecutive_days", "co_buy_flag",
        "grade", "buy_watch", "trim_watch", "review_only", "actual_consecutive_days",
    ]
    streak_cols = [
        "ticker", "name", "market", "pension_streak_direction", "pension_consecutive_days",
        "foreign_streak_direction", "foreign_consecutive_days",
        "cobuy_consecutive_days", "cosell_consecutive_days", "latest_date", "actual_consecutive_days",
    ]

    with sub1:
        df = build_holdings_target_flow_table(data_dir, output_dir)
        if df.empty:
            st.caption("kr_alpha 보유/타깃 종목 없음 또는 데이터 미생성")
        else:
            view = _apply_filters(
                df,
                market=market_filter,
                holding=holding_map[holding_filter],
                freshness=fresh_map[fresh_filter],
            )
            show_dataframe_readable(
                _pick_cols(view, held_cols),
                height=alpha_list_table_height(len(view)),
                key="flow_held_target",
            )

    with sub2:
        df = build_v2_candidate_flow_table(output_dir)
        if df.empty:
            st.caption("alpha_v2_final_candidates.csv / top30 없음")
        else:
            view = _apply_filters(df, market=market_filter, holding="전체", freshness=fresh_map[fresh_filter])
            show_dataframe_readable(
                _pick_cols(view, v2_cols),
                height=alpha_list_table_height(len(view)),
                key="flow_v2_candidates",
            )

    boards = load_leaderboard_tables(output_dir)
    with sub3:
        df = boards.get("pension_buy", pd.DataFrame())
        if df.empty:
            st.caption("flow_leaderboard_pension.csv 없음 — 전체 분석 실행 후 생성")
        else:
            show_dataframe_readable(_pick_cols(df, lb_cols), height=alpha_list_table_height(len(df)), key="flow_lb_pension")

    with sub4:
        df = boards.get("foreign_buy", pd.DataFrame())
        if df.empty:
            st.caption("flow_leaderboard_foreign.csv 없음")
        else:
            show_dataframe_readable(_pick_cols(df, lb_cols), height=alpha_list_table_height(len(df)), key="flow_lb_foreign")

    with sub5:
        df = boards.get("cobuy", pd.DataFrame())
        if df.empty:
            st.caption("flow_leaderboard_cobuy.csv 없음")
        else:
            show_dataframe_readable(_pick_cols(df, lb_cols), height=alpha_list_table_height(len(df)), key="flow_lb_cobuy")

    with sub6:
        streaks = load_streaks_table(output_dir)
        if streaks.empty:
            st.caption("flow_streaks.csv 없음")
        else:
            view = _apply_filters(streaks, market=market_filter, holding="전체", freshness="전체")
            st.markdown("**연속 순매수 Top**")
            buy_lb = boards.get("streak_buy", pd.DataFrame())
            if not buy_lb.empty:
                show_dataframe_readable(_pick_cols(buy_lb, lb_cols), height=220, key="flow_streak_buy_lb")
            st.markdown("**연속 순매도 Top**")
            sell_lb = boards.get("streak_sell", pd.DataFrame())
            if not sell_lb.empty:
                show_dataframe_readable(_pick_cols(sell_lb, lb_cols), height=220, key="flow_streak_sell_lb")
            st.markdown("**전체 streak 상세**")
            show_dataframe_readable(
                _pick_cols(view, streak_cols),
                height=alpha_list_table_height(len(view)),
                key="flow_streaks_all",
            )

    with sub7:
        held, info = load_trim_watch_tables(output_dir)
        st.markdown("**held_or_target** — 보유/타깃 검토 대상")
        if held.empty:
            st.caption("Trim Watch held 없음")
        else:
            show_dataframe_readable(held, height=alpha_list_table_height(len(held)), key="flow_trim_held")
        st.markdown("**informational** — 관찰용, 실행 신호 아님")
        if info.empty:
            st.caption("Trim Watch informational 없음")
        else:
            show_dataframe_readable(info, height=alpha_list_table_height(len(info)), key="flow_trim_info")

    with sub8:
        fresh = load_freshness_summary(output_dir)
        st.json(fresh)
        st.caption("stale flow는 Buy/Trim Watch가 아닌 warning으로 처리됩니다.")
