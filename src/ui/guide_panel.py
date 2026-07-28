from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.ui.nav_shortcuts import (
    SHORTCUT_ALPHA_TARGET,
    SHORTCUT_COMPASS,
    SHORTCUT_DASHBOARD,
    SHORTCUT_GAP,
    SHORTCUT_OPS,
    SHORTCUT_PORTFOLIO,
    SHORTCUT_SETTINGS_API,
    SHORTCUT_SETTINGS_DATA,
    render_shortcut_row,
)
from src.ui.status_banner import render_operational_status


def render_guide_page(data_dir: Path, output_dir: Path) -> None:
    st.header("📖 사용법")
    st.caption("투자 나침반 — 규칙 기반 배분·스크리닝·**사람 승인** 실행 보조 (자동매매 없음)")

    render_operational_status(data_dir, output_dir)

    tab_start, tab_daily, tab_menu, tab_files, tab_faq = st.tabs(
        ["빠른 시작", "매일 5분", "메뉴 안내", "출력 파일", "FAQ"]
    )

    with tab_start:
        st.markdown("### 처음 1회만")
        st.markdown(
            """
<div class="guide-step">① <strong>설치.bat</strong> 실행 (최초 1회)</div>
<div class="guide-step">② <strong>투자나침반.bat</strong> → [1] UI 실행</div>
<div class="guide-step">③ <strong>설정</strong> 메뉴 → DART·KRX API 키 저장</div>
<div class="guide-step">④ <strong>대시보드</strong> → ① 데이터 확인 → ② <strong>▶ 전체 분석</strong></div>
""",
            unsafe_allow_html=True,
        )
        render_shortcut_row([SHORTCUT_SETTINGS_API, SHORTCUT_SETTINGS_DATA, SHORTCUT_DASHBOARD], key_prefix="guide_start", columns=3)

        st.markdown("### 이후 매일")
        st.info(
            "**대시보드**만 열어도 됩니다. "
            "평일 08:00 Windows 작업 스케줄러(`MultiAssetDailyPipeline`)가 켜져 있으면 "
            "데이터 갱신·분석이 **자동** 실행됩니다."
        )
        st.code("python scripts/daily_pipeline.py", language="text")

    with tab_daily:
        st.markdown("### 권장 순서 (약 5분)")
        steps = [
            ("1", "상태 확인", "운용 YELLOW/Scope/dry-run · Data Gate RED면 매매 보류"),
            ("2", "전체 분석", "대시보드 ② — 시장지표 체크 후 ▶ 실행 (자동화 시 생략 가능)"),
            ("3", "Executable 확인", "종합 포트 → Gap·실행 — ETF Buy-allowed만 주문 검토"),
            ("4", "운용승인", "Scope·체크리스트·거시 시나리오 확인"),
            ("5", "보유 반영", "매매 후 종합 포트 → positions 저장 → 재분석"),
        ]
        for num, title, detail in steps:
            with st.container(border=True):
                st.markdown(f"**{num}. {title}** — {detail}")

        render_shortcut_row(
            [SHORTCUT_DASHBOARD, SHORTCUT_GAP, SHORTCUT_OPS, SHORTCUT_PORTFOLIO],
            key_prefix="guide_daily",
            columns=4,
        )

        st.divider()
        st.markdown("### Executable vs Research (꼭 구분)")
        c1, c2 = st.columns(2)
        with c1:
            st.success("**Executable (실행 검토)**")
            st.markdown(
                "- ETF·현금·채권 (`trade_actions.csv`)\n"
                "- Scope가 허용할 때만\n"
                "- Trim: gap 1/3, 1회 최대 2%p\n"
                "- 본인 승인 후 소액 주문"
            )
        with c2:
            st.warning("**Research-only (관찰)**")
            st.markdown(
                "- kr_alpha Review-only (theoretical)\n"
                "- 하케다카 50종 추적 점수\n"
                "- QVM 숏리스트·포트 제안\n"
                "- **매수·매도 신호 아님**"
            )

    with tab_menu:
        rows = [
            ("🏠 대시보드", "일일 운용 허브 — 8단계 진행·전체 분석·AI ZIP"),
            ("📖 사용법", "본 페이지"),
            ("🧭 나침반", "레짐·4축·Data Gate·TAA 근거"),
            ("📐 SAA·TAA", "자산군 목표 비중·배분 흐름"),
            ("🔬 알파", "QVM-SR 스크리너 · Target 승인 · **하케다카 50**"),
            ("📁 종합 포트", "보유 편집 · Gap·실행 · 운용승인 · AI보내기 · 검증"),
            ("📈 백테스트", "레짐·Alpha 히스토리 검증"),
            ("⚙️ 설정", "API 키 · 데이터 갱신 · PyKRX/DART"),
        ]
        for name, desc in rows:
            st.markdown(f"- **{name}** — {desc}")

        render_shortcut_row(
            [SHORTCUT_COMPASS, SHORTCUT_ALPHA_TARGET, SHORTCUT_GAP],
            key_prefix="guide_menu",
            columns=3,
        )

        with st.expander("하케다카 50종 사용법"):
            st.markdown(
                """
1. **알파 → 하케다카 50** 탭 — 추적 점수·DART 소각 신호·등급 필터
2. 파이프라인 실행 시 **자동 갱신** (수동 버튼 없음)
3. **리레이팅·목표 수익 매도**는 본인 규칙 — 시스템은 힌트만 제공
4. 거시 시나리오 `reform_delay`면 신규 매수 보류 권고
"""
            )

    with tab_files:
        st.markdown("| 파일 | 용도 |")
        st.markdown("|------|------|")
        files = [
            ("executable_brief.md", "오늘 Executable 요약 (최우선)"),
            ("trade_actions.csv", "종목별 Buy/Wait/Trim"),
            ("final_execution_decision.json", "최종 권위 — Scope·Alpha 상태"),
            ("acceptance_report.json", "운용 승인 AC"),
            ("compass_regime.json", "레짐·Gate"),
            ("macro_scenario.json", "거시 3시나리오"),
            ("research_checklist.json", "리서치 10항 자동"),
            ("hakedaka_scores.csv", "하케다카 추적 점수"),
            ("daily_report.md", "일일 리포트"),
        ]
        for f, u in files:
            st.markdown(f"| `{f}` | {u} |")
        st.caption("위치: `outputs/` 폴더")

    with tab_faq:
        faqs = [
            ("자동으로 주문되나요?", "아니요. 모든 주문은 본인이 증권사에서 실행합니다."),
            ("kr_alpha Replace를 팔아도 되나요?", "Scope가 ETF_ONLY면 theoretical — **실행·매도 금지** 표시입니다."),
            ("Data Gate RED면?", "데이터·검증 탭에서 원인 수정 후 재분석."),
            ("target이 왜 안 바뀌나요?", "알파 → Target 승인에서 **본인 승인** 후만 반영됩니다."),
            ("dry-run이란?", "매일 분석만 돌려 신호 품질 기록. 10영업일 후 실운용 재평가."),
            ("문서는 어디?", "`docs/USER_GUIDE.md` · `ACCEPTANCE_CRITERIA.md`"),
        ]
        for q, a in faqs:
            with st.expander(q):
                st.write(a)

    st.divider()
    st.caption("상세 문서: `docs/USER_GUIDE.md` · 실운용 기준: `docs/ACCEPTANCE_CRITERIA.md`")
