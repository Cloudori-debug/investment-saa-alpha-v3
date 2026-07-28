"""PMI KR manual verified — operator confirmation UI (data gate only, not execution authority)."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.data_refresh.kosis_tier2_manual import (
    load_pmi_kr_manual_meta,
    save_pmi_kr_manual_fields,
    validate_pmi_kr_manual_ready,
)
from src.report.io_utils import read_output_json

# S&P Global — KOSIS에 한국 PMI 시계열 없음, 운영자가 공식 페이지에서 확인
PMI_SP_GLOBAL_HOME = "https://www.pmi.spglobal.com/"
PMI_SP_GLOBAL_PRESS = "https://www.pmi.spglobal.com/Public/Home/PressRelease"
PMI_SP_GLOBAL_KR_SEARCH = (
    "https://www.pmi.spglobal.com/Public/Release/PressReleases"
    "?region=Asia&country=South%20Korea"
)


def render_pmi_kr_manual_panel(data_dir: Path, output_dir: Path) -> None:
    """One-click operator confirm for pmi_kr tier2 manual path."""
    link1, link2, link3 = st.columns(3)
    link1.link_button(
        "🌐 S&P Global PMI (홈)",
        PMI_SP_GLOBAL_HOME,
        use_container_width=True,
        help="공식 PMI 포털",
    )
    link2.link_button(
        "📰 보도자료 (Press Release)",
        PMI_SP_GLOBAL_PRESS,
        use_container_width=True,
        help="최신 Manufacturing PMI 발표 확인",
    )
    link3.link_button(
        "🇰🇷 한국 PMI 보도자료",
        PMI_SP_GLOBAL_KR_SEARCH,
        use_container_width=True,
        help="South Korea 필터 — 수치·발표일 확인 후 아래 입력",
    )

    st.markdown(
        "공식 페이지에서 **South Korea Manufacturing PMI** 수치·관측월을 확인한 뒤 "
        "아래 폼에 입력하세요. (자동 KOSIS 동기화 불가)"
    )

    st.caption(
        "S&P Global PMI는 KOSIS에 없어 **월 1회** 공식 수치 확인 후 승인합니다. "
        "파이프라인 매번 승인 불필요 — `verified=true`는 유지되며, **새 월 PMI 발표 시에만** "
        "수치·날짜 갱신 + 재승인하면 됩니다."
    )

    meta = load_pmi_kr_manual_meta(data_dir)
    validation = validate_pmi_kr_manual_ready(data_dir)
    reeval = read_output_json(output_dir / "pmi_kr_manual_verified_reevaluation.json") or {}
    core = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    dg = read_output_json(output_dir / "data_gate_diagnostics.json") or {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("verified", "✅ true" if validation.get("verified") else "⬜ false")
    c2.metric("data_gate", str(dg.get("data_gate_status") or "—"))
    c3.metric("core_etf", str(core.get("core_etf_permission") or "—"))
    c4.metric("ETF underweight", int(core.get("eligible_etf_underweight_count") or 0))

    if validation.get("verified"):
        st.success(
            f"승인됨 · value={meta.get('value')} · date={meta.get('value_date')} · "
            f"by={meta.get('updated_by') or '—'}"
        )
    else:
        st.warning(f"미승인 — {validation.get('reason', 'verified=false')}")

    with st.expander("현재 tier2 / 게이트 상태", expanded=not validation.get("verified")):
        st.json({
            "pmi_kr_manual": meta,
            "validation": validation,
            "reevaluation_status": reeval.get("status"),
            "data_gate_blockers": dg.get("primary_data_blockers"),
            "stale_fields": dg.get("stale_fields"),
        })

    with st.form("pmi_kr_manual_form", clear_on_submit=False):
        st.markdown("**공식 PMI 수치 입력** (S&P Global Manufacturing PMI)")
        value = st.number_input(
            "PMI 값",
            min_value=0.0,
            max_value=100.0,
            value=float(meta.get("value") or 52.1),
            step=0.1,
            format="%.1f",
        )
        value_date = st.text_input(
            "관측월 말일 (value_date)",
            value=str(meta.get("value_date") or "2026-06-30"),
            help="예: 2026-06-30 (6월 PMI)",
        )
        source = st.text_input(
            "출처 (source)",
            value=str(meta.get("source") or "S&P Global South Korea Manufacturing PMI"),
        )
        source_url = st.text_input(
            "출처 URL / 메모",
            value=str(meta.get("source_url_or_note") or "https://www.pmi.spglobal.com/Public/Home/PressRelease"),
        )
        updated_by = st.text_input("확인자 (updated_by)", value="operator")
        update_reason = st.text_area(
            "사유 (update_reason)",
            value=str(meta.get("update_reason") or "Official PMI manual confirm via UI"),
            height=68,
        )
        confirm = st.checkbox(
            "S&P Global 공식 발표에서 위 수치·날짜를 확인했습니다 (verified=true)",
            value=False,
        )
        col_save, col_apply = st.columns(2)
        save_draft = col_save.form_submit_button("임시 저장 (verified=false)")
        apply_verified = col_apply.form_submit_button(
            "✅ 확인 및 적용 (verified=true + 게이트 재평가)",
            type="primary",
            disabled=not confirm,
        )

    if save_draft:
        save_pmi_kr_manual_fields(
            data_dir,
            verified=False,
            value=value,
            value_date=value_date,
            source=source,
            source_url_or_note=source_url,
            updated_by=updated_by,
            update_reason=update_reason,
        )
        st.success("prefill 저장됨 (verified=false). 승인하려면 체크박스 후 「확인 및 적용」.")
        st.rerun()

    if apply_verified:
        if not confirm:
            st.error("체크박스 확인 후 적용하세요.")
            return
        save_pmi_kr_manual_fields(
            data_dir,
            verified=True,
            value=value,
            value_date=value_date,
            source=source,
            source_url_or_note=source_url,
            updated_by=updated_by,
            update_reason=update_reason,
        )
        from src.validation.pmi_kr_manual_verified_reevaluation import (
            run_pmi_kr_manual_verified_reevaluation,
        )

        doc = run_pmi_kr_manual_verified_reevaluation(data_dir, output_dir)
        st.success("verified=true 적용 · tier2 refresh 및 게이트 재평가 완료")
        st.json({
            "status": doc.get("status"),
            "data_gate": (doc.get("data_gate_diagnostics") or {}).get("status"),
            "core_etf_permission": (doc.get("core_etf_reevaluation") or {}).get("observed_permission"),
            "actual_buy_allowed": (doc.get("actual_buy_trace") or {}).get("final_actual_buy_allowed"),
            "pipeline_rerun_required": (doc.get("final_execution_decision") or {}).get("pipeline_rerun_required"),
        })
        if (doc.get("final_execution_decision") or {}).get("pipeline_rerun_required"):
            st.info(
                "진단상 data_gate가 GREEN이면 **standard 파이프라인 재실행**으로 "
                "`final_execution_decision.json`의 actual_buy_allowed를 갱신하세요."
            )
        st.rerun()
