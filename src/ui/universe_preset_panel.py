from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.alpha.universe_presets import (
    PRESET_ORDER,
    format_krw_eok,
    load_resolved_universe_filter,
    merged_presets,
    preset_summary_rows,
    save_active_preset,
)
from src.config import load_yaml


def render_universe_preset_panel(data_dir: Path) -> None:
    path = data_dir / "universe_filter.yaml"
    if not path.exists():
        st.warning("`universe_filter.yaml` 없음")
        return

    raw = load_yaml(path)
    presets = merged_presets(raw)
    active = str(raw.get("active_preset", "standard"))
    if active not in PRESET_ORDER:
        active = "standard"

    st.subheader("알파 유니버스 — 시총·유동성 프리셋")
    st.caption(
        "KOSPI common 종목 중 시총·거래대금 하한으로 스크리닝 풀을 정합니다. "
        "변경 후 **전체 분석 실행** + 필요 시 **PyKRX 일괄 수집**을 권장합니다."
    )

    st.dataframe(
        pd.DataFrame(preset_summary_rows(raw)),
        use_container_width=True,
        hide_index=True,
    )

    labels = {name: f"{presets[name].get('label', name)}" for name in PRESET_ORDER}
    choice = st.radio(
        "적용 프리셋",
        options=list(PRESET_ORDER),
        index=list(PRESET_ORDER).index(active),
        format_func=lambda k: labels[k],
        horizontal=True,
        key="universe_preset_choice",
    )
    st.info(presets[choice].get("description", ""))

    resolved = load_resolved_universe_filter(path)
    liq = resolved.get("liquidity", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("시총 하한", format_krw_eok(liq.get("min_market_cap_krw", 0)))
    c2.metric("20일 거래대금", format_krw_eok(liq.get("min_20d_avg_trading_value_krw", 0)))
    c3.metric("상장 최소", f"{liq.get('min_listed_days', 252)}일")

    if choice != active:
        if st.button("💾 프리셋 적용", type="primary", key="apply_universe_preset"):
            save_active_preset(path, choice)
            st.success(f"프리셋 `{choice}` 적용됨 — 전체 분석을 다시 실행하세요.")
            st.rerun()
    else:
        st.caption(f"현재 적용: **{labels[active]}**")

    with st.expander("저유동성 패널티 참고"):
        st.markdown(
            "스코어링 시 20일 거래대금 **20억 미만**이면 `저유동성` 패널티(-15)가 붙습니다. "
            "**보수적** 프리셋(20억 하한)은 필터와 패널티가 맞춰져 있습니다."
        )
