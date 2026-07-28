from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.execution_scope import DRY_RUN_REQUIRED_DAYS
from src.operating_state import UI_OPERATING_STATES

_STATE_STYLE = {
    "ERROR": ("error", "❌"),
    "BLOCKED": ("warning", "⛔"),
    "EXECUTE_ETF": ("success", "✅"),
    "EXECUTE_ALPHA": ("success", "✅"),
    "EXECUTE_MIXED": ("success", "✅"),
    "REVIEW_TARGET": ("info", "📋"),
    "NO_ACTION": ("info", "⬜"),
}


def load_operating_summary(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "final_execution_decision.json"
    if not path.exists():
        return None
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("operating_state"):
        return None
    return data


def render_operating_card(output_dir: Path, *, expanded: bool = True) -> dict[str, Any] | None:
    """대시보드·brief와 동일한 「오늘 운용」 1장 요약."""
    final = load_operating_summary(output_dir)
    if not final:
        st.info("② 전체 분석 후 `operating_state`가 표시됩니다.")
        return None

    state = str(final.get("operating_state", "NO_ACTION"))
    kind, icon = _STATE_STYLE.get(state, ("info", "·"))

    with st.container(border=True):
        st.subheader(f"{icon} 오늘 운용 — `{state}`")
        c1, c2, c3 = st.columns(3)
        c1.metric("운용 판정", final.get("system_status", "—"))
        c2.metric("Scope", final.get("execution_scope", "—"))
        c3.metric("dry-run", f"{final.get('dry_run_days', 0)}/{DRY_RUN_REQUIRED_DAYS}")

        if kind == "error":
            st.error(final.get("primary_user_action", ""))
        elif kind == "warning":
            st.warning(final.get("primary_user_action", ""))
        elif state.startswith("EXECUTE"):
            st.success(final.get("primary_user_action", ""))
            st.caption("사용자 승인 · 소액 · 최대 1액션")
        else:
            st.info(final.get("primary_user_action", ""))

        st.markdown(f"**허용**: {final.get('allowed_scope_label', '—')}")
        forbidden = final.get("forbidden_actions") or []
        if forbidden:
            st.markdown(f"**금지**: {', '.join(forbidden[:3])}" + (" …" if len(forbidden) > 3 else ""))

        candidates = final.get("executable_candidates") or []
        if candidates:
            st.markdown("**실행 후보**")
            for row in candidates[:5]:
                st.write(
                    f"- {row.get('name', row.get('ticker'))} (`{row.get('ticker')}`): "
                    f"**{row.get('action')}**"
                )
        else:
            st.caption("실행 후보: 없음")

        blocked = final.get("blocked_reasons") or []
        if blocked:
            st.markdown(f"**차단 사유**: {' · '.join(blocked[:4])}")

        caution = final.get("caution_reasons") or []
        if caution:
            st.markdown(f"**주의**: {' · '.join(caution)}")

        secondary = final.get("secondary_tasks") or []
        if secondary:
            st.markdown(f"**보조 확인**: {' · '.join(secondary)}")

        st.caption(f"다음: {final.get('next_required_step', '—')}")

        if state not in UI_OPERATING_STATES and expanded:
            st.caption(f"(확장 상태 `{state}` — FULL_WITH_ALPHA 단계용)")

    return final
