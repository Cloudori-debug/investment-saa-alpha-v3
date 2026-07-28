from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report
from src.operational_checklist import build_real_investment_checklist
from src.validation.dry_run_log import load_dry_run_summary

OVERALL_ICON = {"GREEN": "✅", "YELLOW": "⚠️", "RED": "❌"}
STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "todo": "⬜"}


def render_operations_page(data_dir: Path, output_dir: Path) -> None:
    st.header("운용 승인 · Dry-run")
    st.caption("기능 추가 동결 — AC 검증 + 10~20영업일 신호 관찰 단계")

    if st.button("🔒 운용 승인 검증 (AC)", type="primary"):
        report = run_acceptance_check(data_dir, output_dir)
        write_acceptance_report(report, output_dir / "acceptance_report.json")
        st.session_state["acceptance_report"] = report.to_dict()
        st.rerun()

    ac_path = output_dir / "acceptance_report.json"
    ac = st.session_state.get("acceptance_report")
    if ac is None and ac_path.exists():
        ac = json.loads(ac_path.read_text(encoding="utf-8"))
    if ac is None:
        ac = run_acceptance_check(data_dir, output_dir).to_dict()

    overall = ac.get("overall", "YELLOW")
    st.metric(
        "운용 승인",
        f"{OVERALL_ICON.get(overall, '·')} {overall}",
        delta=ac.get("execution_scope", "—"),
    )
    st.caption(f"Alpha: {ac.get('alpha_approval', '—')} · dry-run {ac.get('dry_run_days', 0)}/10일")

    st.info(ac.get("operational_verdict", ""))

    st.divider()
    st.subheader("리서치 자동 체크리스트 (하케다카·거시)")
    st.caption("PwC·DOCX·DART 교차검증 — 실행 신호 아님. 파이프라인 실행 시 자동 갱신")
    rc_path = output_dir / "research_checklist.json"
    macro_path = output_dir / "macro_scenario.json"
    if macro_path.exists():
        macro = json.loads(macro_path.read_text(encoding="utf-8"))
        sid = macro.get("scenario_id", "")
        icon = {"reform_success": "✅", "reform_delay": "⚠️", "stress_failure": "❌"}.get(sid, "·")
        st.write(f"{icon} **거시 시나리오**: {macro.get('label', '—')} — {macro.get('ops_hint', '')}")
    if rc_path.exists():
        rc = json.loads(rc_path.read_text(encoding="utf-8"))
        for item in rc.get("items", []):
            st.write(f"{STATUS_ICON.get(item['status'], '·')} **{item['label']}** — {item['detail']}")
    else:
        st.caption("전체 분석 또는 일일 파이프라인 실행 후 자동 생성됩니다.")

    st.divider()
    st.subheader("실투자 1주일 체크리스트")
    st.caption("ETF·비중 점검 소액 실투자용 — kr_alpha·전액 리밸런싱은 dry-run 10일 후")
    for item in build_real_investment_checklist(data_dir, output_dir):
        st.write(f"{STATUS_ICON.get(item.status, '·')} **{item.label}** — {item.detail}")

    brief = output_dir / "executable_brief.md"
    if brief.exists():
        with st.expander("Executable 요약 (executable_brief.md)"):
            st.markdown(brief.read_text(encoding="utf-8"))

    for item in ac.get("items", []):
        icon = OVERALL_ICON.get("GREEN" if item["status"] == "pass" else "YELLOW" if item["status"] == "warn" else "RED", "·")
        with st.expander(f"{icon} {item['id']} {item['name']} — {item['message']}"):
            if item.get("detail"):
                st.json(item["detail"])

    st.divider()
    st.subheader("PMI KR · Dry-run")
    from src.ui.nav_shortcuts import SHORTCUT_PMI, shortcut_button

    st.caption("PMI KR 수동 확인은 상단 메뉴 **PMI** 탭에서 진행합니다.")
    shortcut_button(SHORTCUT_PMI, key="ops_goto_pmi")

    st.divider()
    st.subheader("Dry-run 로그")
    summary = load_dry_run_summary(output_dir)
    st.metric("누적 영업일", f"{summary['days']} / 10 목표")
    if summary["entries"]:
        df = pd.DataFrame(summary["entries"])
        cols = [c for c in [
            "date", "overall_status", "execution_scope", "alpha_approval",
            "data_gate", "applied_regime", "action_count", "buy_allowed_count",
        ] if c in df.columns]
        st.dataframe(df[cols].tail(20), use_container_width=True)
    else:
        st.caption("전체 분석 실행 시 `dry_run_log.jsonl`에 자동 기록됩니다.")

    st.divider()
    st.markdown("""
**현재 단계 (1→2→3)**  
1. ~~기능 MVP~~ ✅  
2. **데이터 신뢰성 + dry-run** ← 지금  
3. 제한 운용 (ETF·자산군 우선)

상세: `docs/ACCEPTANCE_CRITERIA.md` · `docs/MVP_SPEC.md` v1.0 FROZEN
""")
