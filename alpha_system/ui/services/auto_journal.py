"""Auto-journal system-originated events (append-only, deduped via runtime)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from alpha_system.entry.evaluate import EntryEvaluation
from alpha_system.entry.models import EntryActionType, TrancheState
from alpha_system.journal import append_record
from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.runtime_state import RuntimeState

# --- Gap audit (before fill) ---
# Already journaled when journal=True on evaluate/attempt_execute/swap/exit modify:
#   EXECUTE, MARK_READY, FREEZE, WARN_BLOCKED (attempt_execute), SWAP_CANDIDATE,
#   TARGET_VALUATION_MODIFY, WARN_*, T2_EVENT_*, THESIS_*, GO_LIVE_DECLARE (UI)
# Previously missing on dashboard path (evaluate journal=False):
#   tranche state transitions, trigger_met flips, hard-rule WARN on eval actions,
#   cap warn/over, data refresh result, go-live blocked attempts
# Manual T2/thesis: intentionally NOT auto (2-step confirm remains)


def sync_system_journal(
    *,
    as_of: date,
    runtime: RuntimeState,
    entry_eval: EntryEvaluation,
    portfolio_rows: list[PortfolioRow],
    pre_launch: bool,
) -> list[str]:
    """Compare prior runtime snapshot → append new system events. Returns kinds written."""
    written: list[str] = []
    prior_states = dict(runtime.journaled_tranche_states or {})
    prior_met = dict(runtime.journaled_trigger_met or {})
    prior_cap = dict(runtime.journaled_cap_tone or {})

    new_states: dict[str, str] = {}
    new_met: dict[str, bool] = {}

    for st in entry_eval.statuses:
        tid = st.tranche_id.value if hasattr(st.tranche_id, "value") else str(st.tranche_id)
        state_s = st.state.value
        new_states[tid] = state_s
        new_met[tid] = bool(st.trigger_met)

        old_state = prior_states.get(tid)
        if old_state is not None and old_state != state_s:
            append_record(
                action_kind="TRANCHE_STATE_TRANSITION",
                as_of=as_of,
                subject=tid,
                rationale=f"{old_state} → {state_s}",
                trigger_snapshot={"from": old_state, "to": state_s, "pre_launch": pre_launch},
                payload={"detail": st.detail or ""},
            )
            written.append("TRANCHE_STATE_TRANSITION")

        old_met = prior_met.get(tid)
        if old_met is not None and old_met != bool(st.trigger_met):
            kind = "TRIGGER_FIRED" if st.trigger_met else "TRIGGER_CLEARED"
            append_record(
                action_kind=kind,
                as_of=as_of,
                subject=tid,
                rationale=st.detail or kind,
                trigger_snapshot={"trigger_met": st.trigger_met, "state": state_s},
                payload={},
            )
            written.append(kind)

        # First observation: transitions handle subsequent flips; no seed flood

    for act in entry_eval.actions:
        if act.blocked or act.action_type == EntryActionType.WARN_BLOCKED:
            key = f"{act.tranche_id.value}:{act.reason}"
            seen = set(runtime.journaled_block_keys or [])
            if key not in seen:
                append_record(
                    action_kind="HARD_RULE_BLOCK",
                    as_of=as_of,
                    subject=act.tranche_id.value,
                    rationale=act.reason,
                    trigger_snapshot={"action_type": act.action_type.value},
                    payload={"weight": act.weight, "blocked": True},
                )
                seen.add(key)
                runtime.journaled_block_keys = list(seen)
                written.append("HARD_RULE_BLOCK")

    new_cap: dict[str, str] = {}
    for row in portfolio_rows:
        tone = "danger" if row.cap_over else ("warn" if row.cap_near else "ok")
        new_cap[row.ticker] = tone
        old = prior_cap.get(row.ticker)
        if old == tone:
            continue
        if tone == "warn":
            append_record(
                action_kind="CAP_WARN",
                as_of=as_of,
                subject=row.ticker,
                rationale=f"비중 {row.weight_pct}% near cap {row.cap_pct}%",
                payload={"weight_pct": row.weight_pct, "cap_pct": row.cap_pct},
            )
            written.append("CAP_WARN")
        elif tone == "danger":
            append_record(
                action_kind="CAP_OVER",
                as_of=as_of,
                subject=row.ticker,
                rationale=f"비중 {row.weight_pct}% >= cap {row.cap_pct}%",
                payload={"weight_pct": row.weight_pct, "cap_pct": row.cap_pct},
            )
            written.append("CAP_OVER")

    runtime.journaled_tranche_states = new_states
    runtime.journaled_trigger_met = {k: bool(v) for k, v in new_met.items()}
    runtime.journaled_cap_tone = new_cap
    return written


def journal_data_refresh(*, as_of: date, ok: bool, message: str, detail: dict[str, Any]) -> None:
    append_record(
        action_kind="DATA_REFRESH_OK" if ok else "DATA_REFRESH_FAIL",
        as_of=as_of,
        subject="*",
        rationale=message,
        payload={"detail": detail},
    )


def journal_go_live_blocked(*, as_of: date, items: list[str]) -> None:
    append_record(
        action_kind="GO_LIVE_ATTEMPT_BLOCKED",
        as_of=as_of,
        subject="*",
        rationale="checklist gate blocked go-live",
        payload={"items": items},
    )
