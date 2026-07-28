from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.validation.system_health import run_system_health, write_health_report

STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⬜"}
OVERALL_LABEL = {"pass": "정상", "warn": "주의", "fail": "불충분"}


def render_health_page(data_dir: Path, output_dir: Path) -> None:
    st.header("시스템 검증")
    st.caption("MVP 필수 입력·지표 커버리지·출력 산출물·판정 논리 전제조건 점검")

    col_run, col_kospi = st.columns(2)
    with col_run:
        if st.button("🔍 전체 검증 실행", type="primary", use_container_width=True):
            report = run_system_health(data_dir, output_dir)
            write_health_report(report, output_dir / "system_health.json")
            st.session_state["health_report"] = report.to_dict()
            st.rerun()
    with col_kospi:
        as_of = st.text_input("KOSPI 갱신 as_of", value="", placeholder="비우면 최근 영업일")
        if st.button("📈 시장 지표 전체 갱신 (KOSPI+글로벌)", use_container_width=True):
            from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

            try:
                result = refresh_all_market_indicators(data_dir, as_of=as_of or None)
                if result.updated_fields:
                    st.success(f"갱신: {', '.join(result.updated_fields)} ({result.as_of})")
                for w in result.warnings:
                    st.warning(w)
                for e in result.errors:
                    st.error(e)
            except Exception as exc:
                st.error(str(exc))

    report_dict = st.session_state.get("health_report")
    if report_dict is None and (output_dir / "system_health.json").exists():
        import json
        report_dict = json.loads((output_dir / "system_health.json").read_text(encoding="utf-8"))
    if report_dict is None:
        report_dict = run_system_health(data_dir, output_dir).to_dict()

    overall = report_dict.get("overall", "warn")
    summary = report_dict.get("summary", {})
    st.metric(
        "종합 판정",
        OVERALL_LABEL.get(overall, overall),
        delta=f"pass {summary.get('pass', 0)} · warn {summary.get('warn', 0)} · fail {summary.get('fail', 0)}",
    )

    st.divider()

    modules = sorted({c["module"] for c in report_dict.get("checks", [])})
    selected = st.multiselect("모듈 필터", modules, default=modules)

    for check in report_dict.get("checks", []):
        if check["module"] not in selected:
            continue
        icon = STATUS_ICON.get(check["status"], "·")
        with st.expander(f"{icon} [{check['module']}] {check['name']} — {check['message']}", expanded=check["status"] == "fail"):
            st.write(check.get("message", ""))
            detail = check.get("detail")
            if detail:
                st.json(detail)

    st.divider()
    st.subheader("모듈별 필수 지표 요약")
    st.markdown("""
| 모듈 | 필수 데이터 | 자동 수집 |
|------|------------|----------|
| **나침반 Tier1** | kospi~gold, vix, usdkrw 등 | KOSPI PyKRX + 글로벌 Yahoo |
| **Tier2** | macro_tier2.csv 7필드 | FRED/KOSIS API (`tier2_refresh`) |
| **TAA/SAA** | saa_profiles + compass_regime | 파이프라인 산출 |
| **Alpha** | universe, fundamentals, prices | PyKRX bulk + DART |
| **실행** | positions, targets, trigger_rules | 수동 |
""")
