from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.ui.helpers import load_markdown, load_output_json


def render_compass_page(output_dir: Path) -> None:
    st.header("🧭 나침반 — 시장·레짐")
    st.caption("국면·레짐·Data Gate·실행 레벨 — SAA/TAA·알파·실행의 입력")

    data = load_output_json(output_dir, "compass_regime.json")
    if data is None:
        st.info("사이드바 **전체 분석 실행** 후 나침반 결과가 표시됩니다.")
        return

    computed = data.get("computed_regime", "—")
    applied = data.get("applied_regime", "—")
    override = data.get("override") or {}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("적용 레짐", applied)
    c2.metric("산출 레짐", computed)
    c3.metric("시장 국면", data.get("computed_market_phase", "—"))
    c4.metric("Data Gate", data.get("data_gate", "—"))
    c5.metric("실행 레벨", data.get("execution_level", "—"))

    c6, c7, c8 = st.columns(3)
    c6.metric("나침반 방향", data.get("compass_direction", "—"))
    c7.metric("Tier2", "ON" if data.get("tier2_used") else "OFF")
    c8.metric("SAA 프로필", data.get("profile", "—"))

    if override.get("active"):
        st.info(
            f"**수동 레짐 우선** — 지표 산출 **{computed}**, "
            f"`market_indicators.csv` regime(**{data.get('manual_regime', '—')}**) → "
            f"배분·실행에 **{applied}** 적용."
        )

    breakdown = data.get("score_breakdown") or []
    if breakdown:
        st.subheader("4축 점수")
        cols = st.columns(min(len(breakdown), 4))
        for i, item in enumerate(breakdown[:4]):
            cols[i].metric(
                item.get("axis", f"축{i+1}"),
                f"{item.get('score', 0):+.2f}",
                delta=item.get("label", ""),
            )

    st.divider()
    report = load_markdown(output_dir, "compass_report.md")
    if report:
        st.markdown(report)
    else:
        st.caption("compass_report.md 없음")
