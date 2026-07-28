"""CECS 티어 배분 Streamlit UI (수동 CECS 입력 → 비중 시뮬레이션)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.catalyst_profile import CatalystTier, StockCatalystProfile, calculate_cecs
from src.config_loader import load_yaml
from src.loaders import load_fundamentals
from src.paths import get_paths
from src.tier_allocator import (
    build_tiered_portfolio,
    portfolio_allocation_warnings,
    profile_from_scores_row,
)


TIER_COLORS = {
    "CORE": "#2ecc71",
    "NEAR": "#3498db",
    "SATELLITE": "#e67e22",
    "HEDGE": "#95a5a6",
    "EXCLUDE": "#bdc3c7",
}


def _load_candidates(output_dir: Path) -> pd.DataFrame:
    path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"ticker": str})


def render_tier_allocation_page() -> None:
    paths = get_paths()
    tw_cfg = load_yaml(paths["config"] / "tier_weighting.yaml")
    fundamentals = load_fundamentals(paths["raw"] / "fundamentals.csv")
    candidates = _load_candidates(paths["output"])

    st.title("티어 배분 (CECS)")
    st.caption(
        "6-팩터 `composite_score` + 촉매 실행확실성(CECS) 하위 지표로 CORE/NEAR/SATELLITE/HEDGE 비중을 시뮬레이션합니다. "
        "실행 게이트·Actual Buy Allowed와 무관한 연구용 UI입니다."
    )

    if candidates.empty:
        st.warning("`alpha_candidates.csv`가 없습니다. 먼저 `python -m src.main`을 실행하세요.")
        return

    max_names = st.slider("대상 종목 수", 3, 12, 7)
    top = candidates.head(max_names).copy()
    top["ticker"] = top["ticker"].astype(str).str.zfill(6)

    st.subheader("CECS 하위 지표 (종목별 수동 조정)")
    profiles: list[StockCatalystProfile] = []
    hedge_tickers: set[str] = set()

    for _, row in top.iterrows():
        ticker = str(row["ticker"])
        with st.expander(f"{row.get('name', ticker)} ({ticker}) — composite={row.get('composite_score', '—')}", expanded=False):
            c1, c2, c3 = st.columns(3)
            disclosure = c1.slider("disclosure_status", 0.0, 1.0, 0.5, 0.05, key=f"d_{ticker}")
            continuity = c2.slider("execution_continuity", 0.0, 1.0, 0.5, 0.05, key=f"c_{ticker}")
            pension = c3.slider("pension_flow_score", 0.0, 1.0, 0.5, 0.05, key=f"p_{ticker}")
            c4, c5, c6 = st.columns(3)
            invest_purpose = c4.slider("investment_purpose_flag", 0.0, 1.0, 0.5, 0.05, key=f"i_{ticker}")
            indep = c5.slider("independent_catalyst_flag", 0.0, 1.0, 0.5, 0.05, key=f"ind_{ticker}")
            policy_dep = c6.slider("policy_dependency_flag", 0.0, 1.0, 0.5, 0.05, key=f"pol_{ticker}")
            hedge_flag = st.checkbox("HEDGE 후보 (펀더멘털 기준 수동 지정)", key=f"h_{ticker}")
            tier_override = st.selectbox(
                "티어 강제 지정 (선택)",
                ["(자동)", "CORE", "NEAR", "SATELLITE", "HEDGE", "EXCLUDE"],
                key=f"tier_{ticker}",
            )
            if hedge_flag:
                hedge_tickers.add(ticker)
            base = profile_from_scores_row(row)
            manual = None if tier_override == "(자동)" else CatalystTier(tier_override)
            profiles.append(
                StockCatalystProfile(
                    ticker=ticker,
                    name=base.name,
                    factor_score_total=base.factor_score_total,
                    disclosure_status=disclosure,
                    execution_continuity=continuity,
                    pension_flow_score=pension,
                    investment_purpose_flag=invest_purpose,
                    independent_catalyst_flag=indep,
                    policy_dependency_flag=policy_dep,
                    manual_tier_override=manual,
                )
            )

    allocation = build_tiered_portfolio(profiles, hedge_tickers, tw_cfg=tw_cfg)
    meta = allocation.get("_meta") or {}
    warnings = meta.get("warnings") or portfolio_allocation_warnings(allocation, tw_cfg=tw_cfg)

    for w in warnings:
        st.warning(w)
    if meta:
        m1, m2, m3 = st.columns(3)
        m1.metric("배분 합계", f"{meta.get('allocation_weight_sum', 0):.1%}")
        m2.metric("미배분(현금)", f"{meta.get('unallocated_weight', 0):.1%}")
        m3.metric("100% 충족", "예" if meta.get("allocation_complete") else "아니오")

    rows = []
    for ticker, item in allocation.items():
        if ticker == "_meta" or not isinstance(item, dict):
            continue
        rows.append({
            "ticker": ticker,
            "name": item["name"],
            "tier": item["tier"],
            "cecs": item["cecs"],
            "composite_score": item["composite_score"],
            "weight": f"{item['weight'] * 100:.1f}%",
            "weight_num": item["weight"],
        })
    df = pd.DataFrame(rows).sort_values("weight_num", ascending=False)

    st.subheader("티어별 배분 결과")
    st.dataframe(
        df.drop(columns=["weight_num"]),
        use_container_width=True,
        column_config={
            "tier": st.column_config.TextColumn("티어"),
        },
    )

    core_near = df[df["tier"].isin(["CORE", "NEAR"])]["weight_num"].sum()
    satellite = df[df["tier"] == "SATELLITE"]["weight_num"].sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("CORE+NEAR", f"{core_near:.1%}", help="목표 65~75%")
    m2.metric("SATELLITE", f"{satellite:.1%}", help="목표 15~20%")
    m3.metric("종목 수", len(df))

    if st.button("JSON 저장 (data/output/tier_allocation.json)"):
        out_path = paths["output"] / "tier_allocation.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(allocation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        st.success(f"저장: {out_path}")


def main() -> None:
    st.set_page_config(page_title="Alpha Tier Allocation", layout="wide")
    render_tier_allocation_page()


if __name__ == "__main__":
    main()
