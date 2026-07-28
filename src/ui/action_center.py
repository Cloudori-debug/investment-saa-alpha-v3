"""운영자 액션 센터 — 기존 게이트/승인 신호를 앱 최상단에 집약."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "warning", "info"]


@dataclass
class ActionItem:
    id: str
    severity: Severity
    title: str
    detail: str
    action_label: str
    nav_target: str | None
    nav_focus: str | None = None
    inline_action: str | None = None


def _blocking_streak_days(output_dir: Path) -> int | None:
    from src.report.io_utils import read_output_json

    blocking = read_output_json(output_dir / "core_etf_blocking_duration.json") or {}
    streak = blocking.get("core_etf_restricted_days_current_streak")
    if streak is None:
        core_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
        bd = core_doc.get("blocking_duration") or {}
        streak = bd.get("streak_days")
    return int(streak) if streak is not None else None


def _load_policy_cap_from_outputs(output_dir: Path) -> dict | None:
    from src.report.io_utils import read_output_json

    decision = read_output_json(output_dir / "final_execution_decision.json") or {}
    cap = decision.get("policy_cap")
    if isinstance(cap, dict) and cap:
        return cap
    return None


def collect_action_items(data_dir: Path, output_dir: Path) -> list[ActionItem]:
    from src.alpha.target_draft_bridge import default_target_draft_path, is_target_draft_pending
    from src.data_refresh.kosis_tier2_manual import validate_pmi_kr_manual_ready
    from src.report.io_utils import read_output_json
    from src.ui.nav_shortcuts import FOCUS_ALPHA_TARGET

    items: list[ActionItem] = []

    pmi_validation = validate_pmi_kr_manual_ready(data_dir)
    core_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    restriction_reasons = core_doc.get("restriction_reasons") or []
    if not pmi_validation.get("ready") and "data_gate=YELLOW→core_etf_REVIEW_ONLY" in restriction_reasons:
        streak = _blocking_streak_days(output_dir)
        streak_text = f" ({streak}일째)" if streak is not None else ""
        items.append(
            ActionItem(
                id="pmi_kr_manual_confirm",
                severity="warning",
                title="PMI KR 데이터 확인 필요",
                detail=(
                    f"data_gate=YELLOW로 ETF 매수 {core_doc.get('eligible_etf_underweight_count', 0)}건 차단 중"
                    f"{streak_text} — S&P Global 공식 수치 확인 후 승인 필요"
                ),
                action_label="PMI 확인으로 이동",
                nav_target="PMI",
                nav_focus=None,
            )
        )

    draft_path = default_target_draft_path()
    if is_target_draft_pending(data_dir, draft_path):
        items.append(
            ActionItem(
                id="target_draft_pending",
                severity="critical",
                title="타겟 포트폴리오 승인 대기",
                detail="새 제안이 있습니다 — 검토 후 승인해야 target_portfolio.csv에 반영됩니다.",
                action_label="승인 화면으로 이동",
                nav_target="알파",
                nav_focus=FOCUS_ALPHA_TARGET,
            )
        )

    cap_state = _load_policy_cap_from_outputs(output_dir)
    if cap_state:
        days_left = cap_state.get("days_to_expiry")
        expiry_status = cap_state.get("expiry_status", "NONE")
        cap_reason = cap_state.get("cap_reason") or ""
        if expiry_status == "EXPIRED_REVIEW_REQUIRED":
            items.append(
                ActionItem(
                    id="policy_cap_expired",
                    severity="critical",
                    title="정책 캡(레짐 오버라이드) 만료 — 재검토 필요",
                    detail=f"수동 레짐 오버라이드가 만료되었습니다: {cap_reason}",
                    action_label="나침반/레짐 화면으로 이동",
                    nav_target="나침반",
                )
            )
        elif expiry_status == "ACTIVE" and days_left is not None and 0 <= int(days_left) <= 14:
            items.append(
                ActionItem(
                    id="policy_cap_expiring_soon",
                    severity="warning",
                    title=f"정책 캡 만료 {int(days_left)}일 전",
                    detail="만료 시 자동으로 컴퓨티드 레짐으로 복귀합니다 — 계속 유지할지 사전 검토 권장.",
                    action_label="나침반/레짐 화면으로 이동",
                    nav_target="나침반",
                )
            )

    return items


def render_action_center(data_dir: Path, output_dir: Path) -> None:
    import streamlit as st

    from src.ui.nav_shortcuts import navigate

    items = collect_action_items(data_dir, output_dir)
    if not items:
        return

    today = date.today().isoformat()
    dismissed = st.session_state.get("action_center_dismissed_date")
    if dismissed == today and st.session_state.get("action_center_dismissed_all"):
        items = [i for i in items if i.severity == "critical"]
        if not items:
            return

    has_dialog = hasattr(st, "dialog")

    def _body() -> None:
        for item in items:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[item.severity]
            st.markdown(f"{icon} **{item.title}**")
            st.caption(item.detail)
            if st.button(item.action_label, key=f"ac_{item.id}"):
                if item.nav_target:
                    navigate(item.nav_target, focus=item.nav_focus)
            st.divider()
        if st.button("오늘 하루 닫기 (긴급 항목 제외)", key="ac_dismiss_today"):
            st.session_state["action_center_dismissed_date"] = today
            st.session_state["action_center_dismissed_all"] = True
            st.rerun()

    if has_dialog:

        @st.dialog(f"확인이 필요합니다 ({len(items)}건)")
        def _popup() -> None:
            _body()

        if st.session_state.get("action_center_popup_shown_date") != today:
            st.session_state["action_center_popup_shown_date"] = today
            _popup()
        else:
            with st.expander(
                f"⚠️ 확인 필요 {len(items)}건",
                expanded=any(i.severity == "critical" for i in items),
            ):
                _body()
    else:
        with st.container(border=True):
            st.markdown(f"### ⚠️ 확인이 필요합니다 ({len(items)}건)")
            _body()
