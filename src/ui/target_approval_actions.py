"""Shared Target 승인 UI — dashboard Step ⑥ · 알파 → Target 승인 탭 공통."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.ui.table_display import (
    show_dataframe_readable,
    target_approval_table_height,
    target_proposal_diff_column_config,
)

_TARGET_APPROVAL_CONFIRM_LABEL = "변경 내용 검토·동의 (diff·kr_alpha 비중 확인 완료)"


def _inject_target_approval_prominence_styles() -> None:
    if st.session_state.get("_target_approval_prominence_styles"):
        return
    st.session_state["_target_approval_prominence_styles"] = True
    st.markdown(
        """
        <style>
        .target-approval-heading {
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.35;
            margin: 0 0 0.35rem 0;
            color: #fafafa;
        }
        .target-approval-sub {
            font-size: 0.95rem;
            color: #ced4da;
            margin: 0 0 0.85rem 0;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.target-approval-anchor)
            label[data-testid="stCheckboxLabel"] p {
            font-size: 1.12rem !important;
            font-weight: 600 !important;
            line-height: 1.4 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.target-approval-anchor)
            div[data-testid="stCheckbox"] {
            padding: 0.35rem 0 0.65rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_proposal_preview(
    proposal: Any,
    *,
    key_prefix: str,
    diff_heading: str = "**전체 target 변경 diff** (ETF·현금 포함)",
) -> None:
    for w in proposal.warnings:
        st.warning(w)
    if proposal.changes:
        st.markdown(diff_heading)
        diff_df = pd.DataFrame([c.__dict__ for c in proposal.changes])
        show_dataframe_readable(
            diff_df,
            column_config=target_proposal_diff_column_config(),
            height=target_approval_table_height(len(diff_df)),
            key=f"{key_prefix}_diff",
        )
    c1, c2 = st.columns(2)
    c1.metric("kr_alpha 합 (제안)", f"{proposal.kr_alpha_sum:.1f}%")
    if proposal.kr_alpha_budget is not None:
        c2.metric("Compass 예산", f"{proposal.kr_alpha_budget:.1f}%")


def render_target_approval_actions(
    proposal: Any,
    data_dir: Path,
    output_dir: Path,
    *,
    key_prefix: str,
    session_proposal_key: str | None = None,
) -> None:
    """체크박스 + 승인자 + 승인 반영 (target_write_audit 경유)."""
    from src.alpha.target_bridge import apply_proposed_target
    from src.alpha.target_portfolio_guard import TargetPortfolioWriteBlockedError

    st.divider()
    st.markdown("### ✅ 타겟 승인")

    with st.container(border=True):
        _inject_target_approval_prominence_styles()
        st.markdown(
            '<span id="target-approval-gate" class="target-approval-anchor"></span>'
            '<p class="target-approval-heading">📋 변경 내용 검토·동의</p>'
            '<p class="target-approval-sub">위 diff·비중 표를 확인한 뒤 아래에 동의하고 '
            "✅ 승인 반영을 누르세요.</p>",
            unsafe_allow_html=True,
        )
        st.warning("백업 후 반영됩니다. 주문 실행은 별도 사람 판단입니다.")
        st.caption(
            "Actual Buy Allowed=0 또는 NO_TRADE여도 target 반영은 가능하나, "
            "신규매수 실행 권한은 별도 gate에서 차단될 수 있습니다."
        )
        if st.checkbox(_TARGET_APPROVAL_CONFIRM_LABEL, key=f"{key_prefix}_confirm"):
            auto_reanalyze = st.checkbox(
                "승인 후 ▶ 전체 분석 자동 실행 (시장지표 OFF · STANDARD)",
                value=True,
                key=f"{key_prefix}_auto_reanalyze",
            )
            approver = str(
                st.text_input(
                    "승인자 (이름 또는 이니셜 · 필수)",
                    value="",
                    key=f"{key_prefix}_approver",
                    help="빈 값·기본 human 자동 대입 없음. 감사 로그에 그대로 기록됩니다.",
                )
                or ""
            ).strip()
            if not approver:
                st.warning("승인자 이름 또는 이니셜을 입력해야 승인 반영할 수 있습니다.")
            if st.button(
                "✅ 승인 반영",
                key=f"{key_prefix}_apply",
                type="primary",
                use_container_width=True,
                disabled=not bool(approver),
            ):
                try:
                    result = apply_proposed_target(
                        proposal,
                        data_dir / "target_portfolio.csv",
                        backup_dir=data_dir / "backups",
                        approved_by=approver,
                        data_dir=data_dir,
                        output_dir=output_dir,
                        writer_module="ui.target_approval_actions",
                    )
                except TargetPortfolioWriteBlockedError as exc:
                    st.error(str(exc))
                    st.info("재편입 금지 종목은 proposal에서 자동 제외됩니다. 미리보기를 다시 생성하세요.")
                except Exception as exc:
                    st.error(f"승인 반영 실패: {exc}")
                else:
                    n = int((result.audit or {}).get("write_material_change_count") or 0)
                    st.success(f"target_portfolio.csv 반영 완료 — {n}종 가중치 변경")
                    if session_proposal_key:
                        st.session_state.pop(session_proposal_key, None)
                    st.session_state.pop("target_proposal", None)
                    if auto_reanalyze:
                        from src.ui.pipeline_actions import run_post_target_approval_analysis
                        from src.ui.run_progress_panel import StreamlitRunProgress, render_run_summary

                        progress = StreamlitRunProgress("standard")
                        with st.spinner("승인 반영 후 전체 분석 실행 중 (시장지표 OFF)…"):
                            try:
                                analysis = run_post_target_approval_analysis(
                                    data_dir,
                                    output_dir,
                                    progress=progress,
                                )
                            except Exception as exc:
                                st.error(f"분석 실행 실패: {exc}")
                                st.info(
                                    "target은 이미 반영되었습니다. **대시보드 ②**에서 "
                                    "시장지표 OFF 후 **▶ 전체 분석**을 수동 실행하세요."
                                )
                            else:
                                render_run_summary(
                                    output_dir,
                                    run_mode=analysis.run_mode,
                                    actual_buy_allowed=analysis.actual_buy_allowed,
                                    advisory_note=analysis.advisory_note,
                                    prof=analysis.runtime_profile,
                                )
                                st.session_state["dash_last_run_summary"] = {
                                    "run_mode": analysis.run_mode,
                                    "actual_buy_allowed": analysis.actual_buy_allowed,
                                    "advisory_note": analysis.advisory_note,
                                    "runtime_profile": analysis.runtime_profile,
                                }
                    else:
                        st.info(
                            "분석은 자동 실행하지 않았습니다. **대시보드 ②**에서 "
                            "시장지표 OFF 후 **▶ 전체 분석**을 실행하세요."
                        )
        else:
            st.info("👆 **변경 내용 검토·동의**를 선택하면 승인 반영 버튼이 표시됩니다.")
