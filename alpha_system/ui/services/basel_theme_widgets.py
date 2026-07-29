"""Streamlit render helpers for Basel theme timeline (Review-only)."""

from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st

from alpha_system.ui.services.basel_theme_board import (
    PH4_CHECKLIST,
    build_basel_theme_board,
    rows_as_table_dicts,
    save_ph4_anchor,
)


def render_basel_theme_board(ctx: Any, *, key_prefix: str = "basel") -> None:
    """Read-only timeline + Ph4 anchor checklist. No Core/target writes."""
    import pandas as pd

    root = ctx.root
    as_of = getattr(ctx, "as_of", None) or date.today()
    board = build_basel_theme_board(root, as_of=as_of)

    with st.container(border=True):
        st.subheader("바젤·건전성 테마 시계열")
        st.caption(
            "방향 Hard · 날짜 Soft · 선진입=목표 6개월 전 관찰만 · "
            "자동매매·Core 순위·목표 포트 변경 없음"
        )
        st.caption(board.summary)
        if board.active_themes:
            st.markdown("**지금 선진입·관찰 창이 열린 테마:** " + " · ".join(board.active_themes))

        st.dataframe(
            pd.DataFrame(rows_as_table_dicts(board)),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Ph4 앵커 — 공식·공시 체크 (자본하한 k%)", expanded=not board.ph4.anchored):
            st.caption(
                "언론의 65%/70% 연도만으로 T0를 찍지 않습니다. "
                "아래 공식·공시 중 핵심을 체크하고 적용일을 넣으면 "
                "Ph4·Ph5 선진입 창(T−6M)이 열립니다."
            )
            ph4 = board.ph4
            new_checks: dict[str, bool] = {}
            for cid, label in PH4_CHECKLIST:
                new_checks[cid] = st.checkbox(
                    label,
                    value=bool(ph4.checks.get(cid)),
                    key=f"{key_prefix}_chk_{cid}",
                )

            c1, c2 = st.columns(2)
            with c1:
                t0_default = ph4.t0.isoformat() if ph4.t0 else ""
                t0_s = st.text_input(
                    "적용 목표일 T0 (YYYY-MM-DD)",
                    value=t0_default,
                    key=f"{key_prefix}_t0",
                    help="감독·공시에 적힌 적용 시작일 또는 그 분기 말일",
                )
            with c2:
                k_default = "" if ph4.k_pct is None else str(ph4.k_pct)
                k_s = st.text_input(
                    "적용 자본하한 k (%)",
                    value=k_default,
                    key=f"{key_prefix}_k",
                    help="예: 65 또는 70",
                )
            note = st.text_area(
                "증거 메모 (URL·공시명·쪽수)",
                value=ph4.evidence_note,
                key=f"{key_prefix}_note",
                height=80,
            )

            if st.button("Ph4 앵커 저장 (로컬 Review 노트)", key=f"{key_prefix}_save"):
                t0 = None
                if t0_s.strip():
                    try:
                        t0 = date.fromisoformat(t0_s.strip()[:10])
                    except ValueError:
                        st.error("T0 날짜 형식이 올바르지 않습니다.")
                        return
                k_pct = None
                if k_s.strip():
                    try:
                        k_pct = float(k_s.strip())
                    except ValueError:
                        st.error("k% 숫자 형식이 올바르지 않습니다.")
                        return
                path = save_ph4_anchor(
                    root,
                    checks=new_checks,
                    t0=t0,
                    k_pct=k_pct,
                    evidence_note=note,
                )
                st.success(f"저장됨 · {path.as_posix()} · target·순위 불변")
                st.rerun()

            if board.ph4.anchored:
                st.success(
                    f"앵커 유효 · T0={board.ph4.t0} · k="
                    f"{board.ph4.k_pct if board.ph4.k_pct is not None else '—'} · "
                    "위 표의 Ph4/Ph5 선진입 창을 확인하세요."
                )
            else:
                st.info(
                    "앵커 미충족: T0 입력 + "
                    "(금융위·금감원 안내 **또는** 시행세칙 **또는** 은행 공시) + "
                    "「언론 단독으로 T0 금지」 체크가 필요합니다."
                )

        with st.expander("수혜·부담 읽는 법", expanded=False):
            st.markdown(
                "- **자본하한↑(Ph4~6):** 저위험·담보·우량 쪽 상대 수혜 · "
                "무등급 중소·중견·일부 PF는 부담\n"
                "- **생산적 금융(Ph7):** 발표에 **명시된** 산업만 예외 수혜 — "
                "일정은 그대로여도 테마가 바뀔 수 있음\n"
                "- 익절·논지·제안탈락 바늘이 **본 테마보다 우선**"
            )
