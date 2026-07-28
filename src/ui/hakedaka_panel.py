from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.ui.helpers import load_markdown, load_output_csv


def _load_json(output_dir: Path, name: str) -> dict | None:
    path = output_dir / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_hakedaka_panel(data_dir: Path, output_dir: Path) -> None:
    st.subheader("🇯🇵 하케다카 리스트 — 2026 저평가·자사주 소각 50종")
    st.caption(
        "PDF 투자 해석 + QVM/재무/DART 오버레이 **추적 전용**. "
        "전체 분석·일일 파이프라인 실행 시 **자동 갱신** (수동 버튼 없음)."
    )

    macro = _load_json(output_dir, "macro_scenario.json")
    if macro:
        sid = macro.get("scenario_id", "")
        label = macro.get("label", "—")
        hint = macro.get("ops_hint", "")
        icon = {"reform_success": "✅", "reform_delay": "⚠️", "stress_failure": "❌"}.get(sid, "·")
        st.info(f"{icon} **거시 시나리오**: {label} — {hint}")

    checklist = _load_json(output_dir, "research_checklist.json")
    if checklist:
        s = checklist.get("summary", {})
        st.caption(
            f"리서치 체크리스트 자동: pass {s.get('pass', 0)} · "
            f"warn {s.get('warn', 0)} · fail {s.get('fail', 0)}"
        )

    ver_df = load_output_csv(output_dir, "hakedaka_dart_verification.csv")
    if ver_df is not None and not ver_df.empty:
        with st.expander("DART 자동 검증 (50종)", expanded=True):
            vc1, vc2, vc3, vc4 = st.columns(4)
            vc1.metric("verified", int((ver_df["verification_status"] == "verified").sum()))
            vc2.metric("partial", int((ver_df["verification_status"] == "partial").sum()))
            vc3.metric("failed", int((ver_df["verification_status"] == "failed").sum()))
            vc4.metric("재무 있음", int(ver_df["has_fundamentals"].astype(str).str.lower().eq("true").sum()))
            vcols = [
                c for c in [
                    "no", "name", "ticker", "grade", "verification_status",
                    "dart_signal", "dart_latest_date", "cancel_disclosure",
                    "has_fundamentals", "fundamentals_usable_from", "issues",
                ] if c in ver_df.columns
            ]
            st.dataframe(ver_df[vcols], use_container_width=True, height=280)

    diag_df = load_output_csv(output_dir, "hakedaka_overlap_diagnostics.csv")
    if diag_df is not None and not diag_df.empty:
        with st.expander("Overlap 진단 — 왜 0종인가?", expanded=False):
            overlap = int(diag_df["in_shortlist"].astype(str).str.lower().eq("true").sum())
            st.caption(f"숏리스트 overlap {overlap}종 / shadow 후보 {int(diag_df['shadow_slot_candidate'].astype(str).str.lower().eq('true').sum())}종")
            dcols = [
                c for c in [
                    "name", "ticker", "hakedaka_grade", "dart_verified", "dart_signal",
                    "qvm_score", "qvm_rank", "fail_reason", "liquidity_pass",
                    "financial_pass", "momentum_pass", "in_shortlist", "hakedaka_priority",
                    "eligible_for_watch", "eligible_for_portfolio", "shadow_slot_candidate",
                ] if c in diag_df.columns
            ]
            st.dataframe(diag_df[dcols], use_container_width=True, height=320)

    overlay = _load_json(output_dir, "hakedaka_compass_overlay.json")
    if overlay:
        st.caption(
            f"알파 숏리스트 overlap {overlay.get('alpha_shortlist_overlap', 0)}종 · "
            f"DART verified A {overlay.get('dart_verified_a_count', 0)}종"
        )

    df = load_output_csv(output_dir, "hakedaka_scores.csv")
    if df is None or df.empty:
        st.info("점수 없음 — **전체 분석 실행** 또는 **일일 파이프라인**을 실행하면 자동 생성됩니다.")
        with st.expander("리스트 개요"):
            st.markdown(
                """
**5개 그룹** (PDF 우선순위):  
2 넷넷 > 4 행동주의 > 1 지주·자산 > 3 부동산 > 5 인프라

**등급**: A(12) · B(12) · C(14) · W(12)  
**핵심 후보 예**: 모토닉, 다우데이타, 에스에프에이, KPX홀딩스, 동원산업, 세아제강지주

**자동화**: DART 소각·환원 공시 스캔 → 정합 점수 → 거시 3시나리오 → 체크리스트 10항
"""
            )
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("종목", len(df))
    c2.metric("A등급", int((df["grade"] == "A").sum()))
    c3.metric("보유 overlap", int(df["in_positions"].astype(str).str.lower().eq("true").sum()))
    c4.metric("알파 overlap", int(df["in_alpha_shortlist"].astype(str).str.lower().eq("true").sum()))
    if "dart_signal" in df.columns:
        strong = int((df["dart_signal"] == "strong").sum())
        c5.metric("DART 소각신호", strong)

    grade_filter = st.multiselect(
        "등급 필터",
        options=sorted(df["grade"].dropna().unique()),
        default=["A"],
    )
    bucket_filter = st.multiselect(
        "버킷",
        options=sorted(df["priority_bucket"].dropna().unique()),
        default=[],
    )
    show_held = st.checkbox("보유 종목만", value=False)
    show_alpha = st.checkbox("알파 숏리스트 overlap만", value=False)

    view = df.copy()
    if grade_filter:
        view = view[view["grade"].isin(grade_filter)]
    if bucket_filter:
        view = view[view["priority_bucket"].isin(bucket_filter)]
    if show_held:
        view = view[view["in_positions"].astype(str).str.lower() == "true"]
    if show_alpha:
        view = view[view["in_alpha_shortlist"].astype(str).str.lower() == "true"]

    cols = [
        c for c in [
            "rank", "ticker", "name", "group_id", "grade", "priority_bucket",
            "tracking_score", "thesis_score", "pdf_total", "alpha_score",
            "market_score", "alignment_score", "dart_signal",
            "pbr", "per", "dividend_yield",
            "horizon_short", "horizon_mid", "horizon_long",
            "in_positions", "in_kr_alpha_target", "in_alpha_shortlist",
            "complexity", "invest_type", "memo",
        ] if c in view.columns
    ]
    st.dataframe(view[cols], use_container_width=True, height=420)

    with st.expander("그룹별 요약"):
        if "group_label" in df.columns:
            g = df.groupby(["group_id", "group_label"], as_index=False).agg(
                count=("name", "count"),
                avg_tracking=("tracking_score", "mean"),
                a_grade=("grade", lambda s: (s == "A").sum()),
            )
            st.dataframe(g, use_container_width=True)

    if checklist:
        with st.expander("리서치 체크리스트 (자동)"):
            STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
            for item in checklist.get("items", []):
                st.write(
                    f"{STATUS_ICON.get(item['status'], '·')} **{item['label']}** — {item['detail']}"
                )

    report = load_markdown(output_dir, "hakedaka_report.md")
    if report:
        with st.expander("리포트 (hakedaka_report.md)"):
            st.markdown(report)

    st.caption(
        "자동: `daily_pipeline` · Windows 작업 스케줄러 `MultiAssetDailyPipeline` (평일 08:00)"
    )
