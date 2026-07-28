from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.ui.helpers import load_markdown, load_output_csv

ALPHA_LIMITATIONS = """
**Alpha QVM-SR Lite 백테스트 한계 (투자 전략 미반영)**

| 항목 | Lite 백테스트 | 실제 운용 전략 |
|------|---------------|----------------|
| 종목 수 | 유니버스 전체 quintile | **6~8종** 집중 |
| 교체 규칙 | 없음 | role(core/satellite), TRIM/REPLACE |
| 실행 | 없음 | Data Gate·레짐·**사람 승인** |
| SR 축 | 스코어 proxy | 배당·환원·FCF **정책** 반영 |
| 수익률 | `return_3m` 횡단면 proxy | 익절·손절·승인 지연 미포함 |

→ **팩터 정렬(monotonicity) 검증용**이며, 알파 포트 **성과 예측 불가**.
"""


def _chart_group_targets(df: pd.DataFrame, prefix: str = "") -> None:
    target_cols = [c for c in df.columns if c.endswith("_target")]
    if not target_cols or "date" not in df.columns:
        return
    chart_df = df.set_index("date")[target_cols[:7]]
    chart_df.columns = [c.replace("_target", "") for c in chart_df.columns]
    st.line_chart(chart_df, height=280)


def render_backtest_page(data_dir: Path, output_dir: Path, profile: str) -> None:
    st.header("📈 백테스트")
    st.caption("SAA 정적 · TAA 레짐 경로 · Alpha Lite — 규칙 검증용 (수익률 예측 아님)")

    tab_saa, tab_taa, tab_alpha = st.tabs(["SAA", "TAA", "Alpha QVM-SR"])

    with tab_saa:
        st.subheader("SAA 정적 백테스트")
        st.markdown(
            "선택 SAA 프로필의 **기준 비중**이 history 기간 동안 일정한지 확인합니다. "
            "레짐·TAA 미적용."
        )
        has_hist = (data_dir / "market_indicators_history.csv").exists()
        if not has_hist:
            st.warning("`data/market_indicators_history.csv` 필요")

        if st.button("SAA 백테스트 실행", key="run_saa_bt"):
            from src.backtest.saa_backtest import run_saa_backtest, write_saa_backtest_outputs

            result = run_saa_backtest(data_dir, profile=None)
            write_saa_backtest_outputs(result, output_dir)
            st.success("완료")
            st.rerun()

        saa_df = load_output_csv(output_dir, "saa_backtest_results.csv")
        if saa_df is not None and not saa_df.empty:
            st.dataframe(saa_df.head(10), use_container_width=True)
            _chart_group_targets(saa_df)
        report = load_markdown(output_dir, "saa_backtest_report.md")
        if report:
            st.markdown(report)

    with tab_taa:
        st.subheader("TAA·레짐 백테스트")
        st.markdown(
            "히스토리 각 일자의 **레짐·국면** → SAA + tilt → 최종 자산군 비중 경로. "
            "레짐 전환 빈도·kr_alpha/cash 민감도 확인."
        )
        if not (data_dir / "market_indicators_history.csv").exists():
            st.warning("`data/market_indicators_history.csv` 필요")

        if st.button("TAA 백테스트 실행", key="run_taa_bt"):
            from src.backtest.regime_backtest import run_regime_backtest, write_backtest_outputs

            bt = run_regime_backtest(data_dir, profile=None)
            write_backtest_outputs(bt, output_dir)
            st.success(f"완료 — 레짐 전환 {bt.regime_changes}회")
            st.rerun()

        taa_df = load_output_csv(output_dir, "taa_backtest_results.csv")
        if taa_df is None:
            taa_df = load_output_csv(output_dir, "backtest_results.csv")
        if taa_df is not None and not taa_df.empty:
            if "cash_target" in taa_df.columns and "kr_alpha_target" in taa_df.columns:
                st.line_chart(
                    taa_df.set_index("date")[["cash_target", "kr_alpha_target"]],
                    height=240,
                )
            _chart_group_targets(taa_df)
            st.dataframe(taa_df.tail(15), use_container_width=True)
        report = load_markdown(output_dir, "taa_backtest_report.md") or load_markdown(output_dir, "backtest_report.md")
        if report:
            st.markdown(report)

    with tab_alpha:
        st.subheader("Alpha QVM-SR Lite 백테스트")
        st.markdown(ALPHA_LIMITATIONS)

        has_prices = (data_dir / "prices_history.csv").exists() or (data_dir / "prices.csv").exists()
        if not has_prices:
            st.warning("`data/prices_history.csv` (권장) 또는 `prices.csv` 필요")

        if st.button("Alpha Lite 백테스트 실행", key="run_alpha_bt"):
            from src.backtest.alpha_backtest import run_alpha_lite_backtest, write_alpha_backtest_outputs

            result = run_alpha_lite_backtest(data_dir)
            write_alpha_backtest_outputs(result, output_dir)
            st.success("완료")
            st.rerun()

        summary = load_output_csv(output_dir, "alpha_backtest_summary.csv")
        if summary is not None:
            st.dataframe(summary, use_container_width=True)
        quint = load_output_csv(output_dir, "alpha_backtest_quintiles.csv")
        if quint is not None and "avg_return_3m" in quint.columns:
            st.bar_chart(quint.set_index("quintile")["avg_return_3m"])
        report = load_markdown(output_dir, "alpha_backtest_report.md")
        if report:
            st.markdown(report)
        elif not has_prices:
            st.info("가격 히스토리 확장 후 실행하세요.")
