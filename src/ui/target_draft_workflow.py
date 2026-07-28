from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.ui.table_display import (
    kr_alpha_comparison_column_config,
    kr_alpha_current_column_config,
    show_dataframe_readable,
    target_approval_table_height,
    target_draft_column_config,
)

_ACTION_LABELS = {
    "keep": "유지",
    "add": "신규",
    "trim": "축소",
    "remove": "제외",
    "other": "기타",
}


def _render_action_guide(*, pending: bool) -> None:
    st.markdown("**해야 할 일**")
    if pending:
        st.info(
            "Target draft가 감지되었습니다. "
            "아래에서 비교·diff 확인 후 **이 화면에서 바로 승인 반영**할 수 있습니다. "
            "(알파 → Target 승인 탭에서도 동일하게 가능)"
        )
        st.markdown(
            """
1. **현재 목표 알파** vs **제안 목표 알파 (target_draft)** · **비교 요약** 확인
2. **전체 target diff** 확인 — ETF·현금 등 비-kr_alpha는 그대로, kr_alpha만 교체
3. **변경 내용 검토·동의** → **✅ 승인 반영** (기본: 승인 후 전체 분석 자동 실행)
4. 자동 분석을 끈 경우 **대시보드 ②**에서 시장지표 OFF 후 **▶ 전체 분석**

> 목표 승인 ≠ 실매매. 개별주 매수·매도는 `executable_brief` · execution scope 별도 확인.
"""
        )
    else:
        st.caption("target_draft가 target에 반영됨. 새 draft가 오면 1~4를 다시 진행하세요.")


def _render_action_summary(comparison: pd.DataFrame) -> None:
    from src.alpha.target_draft_bridge import summarize_kr_alpha_draft_actions

    counts = summarize_kr_alpha_draft_actions(comparison)
    if not counts:
        return
    parts = [
        f"**{_ACTION_LABELS.get(k, k)}** {v}종"
        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    st.caption("draft 액션 요약: " + " · ".join(parts))


def render_target_draft_workflow(
    data_dir: Path,
    output_dir: Path,
    draft_path: Path,
    *,
    key_prefix: str = "dash_draft",
) -> None:
    from src.alpha.target_draft_bridge import (
        build_kr_alpha_target_comparison,
        build_proposal_from_draft,
        is_target_draft_pending,
        load_current_kr_alpha_df,
        load_target_draft,
    )
    from src.alpha.target_bridge import write_proposal_outputs
    from src.ui.target_approval_actions import render_proposal_preview, render_target_approval_actions

    pending = is_target_draft_pending(data_dir, draft_path)
    _render_action_guide(pending=pending)

    current_df = load_current_kr_alpha_df(data_dir)
    st.markdown("**현재 목표 알파** — `data/target_portfolio.csv` (kr_alpha)")
    if current_df.empty:
        st.caption("kr_alpha 목표 종목 없음")
    else:
        c1, c2 = st.columns(2)
        c1.metric("종목 수", f"{len(current_df)}")
        c2.metric("합계", f"{current_df['target_weight'].sum():.1f}%")
        show_dataframe_readable(
            current_df,
            columns=("ticker", "name", "target_weight", "min_weight", "max_weight"),
            column_config=kr_alpha_current_column_config(),
            height=target_approval_table_height(len(current_df)),
            key=f"{key_prefix}_current",
        )

    if not draft_path.exists():
        st.info("alpha_portfolio `target_draft.csv` 없음 — Replace/Trim 없으면 ⑧로 진행")
        return

    if not pending:
        st.success("target_draft는 target_portfolio.csv에 반영된 상태입니다.")
        return

    st.warning("미승인 target_draft — `target_portfolio.csv`에 아직 반영되지 않았습니다.")
    st.caption(
        "alpha_portfolio `target_draft.csv` → kr_alpha 목표만 교체 · ETF·현금 등 다른 자산군은 유지"
    )

    try:
        draft_df = load_target_draft(draft_path)
    except Exception as exc:
        st.error(str(exc))
        return

    comparison = build_kr_alpha_target_comparison(
        data_dir, draft_df, draft_path=draft_path
    )
    _render_action_summary(comparison)

    st.markdown("**비교 요약** — 현재 vs 제안 · 종목별 안내")
    if comparison.empty:
        st.caption("비교할 kr_alpha 행 없음")
    else:
        show_dataframe_readable(
            comparison,
            columns=(
                "ticker", "name", "current_pct", "draft_pct", "delta_pct",
                "matrix_action", "change_reason", "user_action",
            ),
            column_config=kr_alpha_comparison_column_config(),
            height=target_approval_table_height(len(comparison)),
            key=f"{key_prefix}_compare",
        )

    st.markdown("**제안 목표 알파 (target_draft)** — 승인 시 kr_alpha가 이렇게 바뀜")
    draft_cols = tuple(
        c for c in (
            "ticker", "name", "target_weight", "matrix_action", "change_reason", "reason",
        )
        if c in draft_df.columns
    ) or ("ticker", "name", "target_weight", "matrix_action")

    d1, d2 = st.columns(2)
    d1.metric("제안 종목 수", f"{len(draft_df)}")
    d2.metric("제안 합계", f"{draft_df['target_weight'].sum():.1f}%")
    show_dataframe_readable(
        draft_df,
        columns=draft_cols,
        column_config=target_draft_column_config(),
        height=target_approval_table_height(len(draft_df)),
        key=f"{key_prefix}_table",
    )

    proposal_key = f"{key_prefix}_proposal"
    if proposal_key not in st.session_state:
        try:
            proposal = build_proposal_from_draft(data_dir, output_dir, draft_path=draft_path)
            write_proposal_outputs(proposal, output_dir)
            st.session_state[proposal_key] = proposal
        except Exception as exc:
            st.error(f"변경안 생성 실패: {exc}")
            return

    proposal = st.session_state.get(proposal_key)
    if proposal:
        st.markdown("**전체 target 변경 diff** — 승인 전 최종 확인")
        render_proposal_preview(proposal, key_prefix=key_prefix)
        render_target_approval_actions(
            proposal,
            data_dir,
            output_dir,
            key_prefix=key_prefix,
            session_proposal_key=proposal_key,
        )

    with st.expander("미리보기 다시 생성 (선택)"):
        c1, c2 = st.columns(2)
        if c1.button("📋 diff 다시 생성", key=f"{key_prefix}_preview", use_container_width=True):
            try:
                proposal = build_proposal_from_draft(data_dir, output_dir, draft_path=draft_path)
                write_proposal_outputs(proposal, output_dir)
                st.session_state[proposal_key] = proposal
                st.success("target_portfolio_proposed.csv 갱신")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if c2.button("⚡ draft 파일 다시 읽기", key=f"{key_prefix}_quick", use_container_width=True):
            try:
                proposal = build_proposal_from_draft(data_dir, output_dir, draft_path=draft_path)
                st.session_state[proposal_key] = proposal
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
