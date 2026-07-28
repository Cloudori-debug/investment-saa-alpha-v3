from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from src.validation.ai_export import (
    CROSS_VALIDATION_PROMPT,
    build_export_zip,
)


def render_export_page(data_dir: Path, output_dir: Path) -> None:
    st.header("AI 교차 검증 내보내기")
    st.caption("GPT·Claude 등에 붙여넣어 규칙·데이터·판정 결과를 독립 검증합니다.")

    if st.button("📦 번들 생성", type="primary"):
        from src.ui.pipeline_actions import run_ai_export

        result = run_ai_export(data_dir, output_dir)
        st.session_state["ai_export_bundle"] = result.bundle
        st.success(f"생성 완료 — as_of {result.as_of}")

    bundle = st.session_state.get("ai_export_bundle")
    if bundle is None and (output_dir / "ai_export_bundle.json").exists():
        import json
        bundle = json.loads((output_dir / "ai_export_bundle.json").read_text(encoding="utf-8"))
        st.session_state["ai_export_bundle"] = bundle

    if not bundle:
        st.info("먼저 **전체 분석 실행** 후 **번들 생성**을 누르세요.")
        return

    overall = (bundle.get("health_report") or {}).get("overall", "—")
    st.metric("건강검증", overall, delta=f"exported {bundle.get('exported_at', '')[:19]}")

    tab_prompt, tab_json, tab_dl = st.tabs(["검증 프롬프트", "JSON 미리보기", "다운로드"])

    with tab_prompt:
        st.markdown("아래 프롬프트 + `ai_export_bundle.json` 내용을 AI에 함께 제공하세요.")
        st.text_area("Cross-validation prompt", CROSS_VALIDATION_PROMPT, height=320, disabled=True)
        st.download_button(
            "프롬프트 다운로드 (.md)",
            CROSS_VALIDATION_PROMPT,
            file_name="validation_prompt.md",
            mime="text/markdown",
        )

    with tab_json:
        import json
        preview = json.dumps(bundle, ensure_ascii=False, indent=2)
        st.text_area("ai_export_bundle.json", preview, height=400)
        st.download_button(
            "JSON 다운로드",
            preview,
            file_name=f"ai_export_{bundle.get('as_of', 'bundle')}.json",
            mime="application/json",
        )

    with tab_dl:
        from src.ui.pipeline_actions import run_ai_export

        if st.button("ZIP 재검증 후 생성", type="primary"):
            try:
                result = run_ai_export(data_dir, output_dir)
                st.session_state["ai_export_bundle"] = result.bundle
                st.session_state["ai_export_zip"] = result.zip_bytes
                st.success(f"export gate PASS — as_of {result.as_of}")
            except Exception as exc:
                st.error(f"export blocked: {exc}")

        zip_bytes = st.session_state.get("ai_export_zip")
        if zip_bytes is None and (output_dir / "export_bundle_validation.json").exists():
            try:
                result = run_ai_export(data_dir, output_dir)
                zip_bytes = result.zip_bytes
                st.session_state["ai_export_zip"] = zip_bytes
                st.session_state["ai_export_bundle"] = result.bundle
            except Exception:
                zip_bytes = None

        if zip_bytes is None:
            zip_bytes = build_export_zip(bundle)
            st.warning("export gate 미통과 ZIP — 'ZIP 재검증 후 생성'을 사용하세요.")
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            "ZIP 다운로드 (JSON + 프롬프트 + 리포트)",
            zip_bytes,
            file_name=f"ai_cross_validation_{stamp}.zip",
            mime="application/zip",
            type="primary",
        )
        st.markdown("**ZIP 포함**")
        st.write("- ai_export_bundle.json")
        st.write("- validation_prompt.md")
        st.write("- system_health.json")
        st.write("- reports/*.md (compass, alpha, daily, triggers)")
