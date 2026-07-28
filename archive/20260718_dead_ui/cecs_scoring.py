"""CECS page removed from nav — redirect to approval hub weekly domain."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.nav import FOCUS_WEEKLY_QUAL, PAGE_APPROVAL, navigate


def render_cecs_scoring(ctx: DashboardContext) -> None:
    del ctx
    st.subheader("CECS 직접 채점은 종료됨")
    st.info(
        "CECS는 주간 정성 리포트 업로드 후 결재함에서 출처 확인·승인합니다. "
        "점수·근거를 직접 기입하는 화면은 더 이상 쓰지 않습니다."
    )
    if st.button("결재함으로", type="primary", key="cecs_to_approval"):
        navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)
