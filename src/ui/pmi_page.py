"""PMI KR — dedicated top-level menu (data gate operator confirm)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.ui.pmi_kr_manual_panel import render_pmi_kr_manual_panel


def render_pmi_page(data_dir: Path, output_dir: Path) -> None:
    st.header("📊 PMI KR 확인")
    st.caption(
        "S&P Global Manufacturing PMI — KOSIS 자동 동기화 불가, **월 1회** 공식 수치 확인 후 승인"
    )
    render_pmi_kr_manual_panel(data_dir, output_dir)
