from __future__ import annotations

import pandas as pd
import streamlit as st

VALIDITY_BG = {
    "proposal": "#d4edda",
    "shortlist": "#fff3cd",
    "weak": "#f8f9fa",
    "pillar_top": "#e7f1ff",
    "reject": "#f8d7da",
}


def style_pillar_leaderboard(df: pd.DataFrame):
    if df.empty or "validity" not in df.columns:
        return df

    def _row_style(row: pd.Series) -> list[str]:
        bg = VALIDITY_BG.get(str(row.get("validity", "")), "")
        return [f"background-color: {bg}" if bg else ""] * len(row)

    return df.style.apply(_row_style, axis=1)


def render_pillar_legend() -> None:
    st.markdown(
        """
**투자 유효성 (행 배경색)**
| 표시 | 의미 |
|------|------|
| 🟢 **포트 제안** | 6~8종 최종 제안 편입 |
| 🟡 **숏리스트** | 4축 중 3축 이상 + 바닥 45점 통과 |
| ⚪ **축우수·종합미달** | 축 Top10이지만 숏리스트 규칙 미충족 (예: V·SR 약함) |
| ⚪ **축 Top만** | 해당 축 상위, 종합 후보 아님 |
| 🔴 **제외/Reject** | 등급·penalty 제외 |
"""
    )


def render_pillar_tabs(leaderboard: pd.DataFrame, *, scored_count: int | None = None) -> None:
    if leaderboard.empty:
        st.caption("축별 순위 데이터 없음 — **전체 분석 실행**")
        return

    if scored_count is not None:
        st.caption(
            f"스크린·스코어 가능 **{scored_count}종** 기준 축별 **Top 10** "
            f"(유니버스가 작으면 Top10 = 전 종목일 수 있음)"
        )

    render_pillar_legend()
    pillars = [
        ("quality", "Q Quality"),
        ("valuation", "V Valuation"),
        ("momentum", "M Momentum"),
        ("shareholder_return", "SR Shareholder Return"),
    ]
    tabs = st.tabs([label for _, label in pillars])
    display_cols = [
        "rank", "ticker", "name", "score", "pillars_pass",
        "total_score", "grade", "validity_label",
    ]
    for tab, (key, _) in zip(tabs, pillars):
        with tab:
            sub = leaderboard[leaderboard["pillar"] == key].copy()
            if sub.empty:
                st.caption("데이터 없음")
                continue
            for col in ("rank", "pillars_pass"):
                if col in sub.columns:
                    sub[col] = pd.to_numeric(sub[col], errors="coerce").fillna(0).astype(int)
            view = sub[[c for c in display_cols if c in sub.columns]]
            st.dataframe(
                style_pillar_leaderboard(view),
                use_container_width=True,
                hide_index=True,
                height=420,
            )
