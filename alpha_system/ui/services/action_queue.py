"""Home action queue assembly — Korean (a/b/c) sentences from UI_COPY."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from datetime import date

from alpha_system.entry.evaluate import EntryEvaluation
from alpha_system.entry.models import EntryActionType, TrancheState
from alpha_system.exit.evaluate import ExitEvaluation
from alpha_system.swap.observe import SwapObserveEvaluation
from alpha_system.ui.services.data_freshness import SourceStatus
from alpha_system.ui.services.judgment_copy import action_sentence, explain_tranche
from alpha_system.ui.services.ui_copy import format_tranche_label


class ActionSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    DANGER = "danger"


@dataclass(frozen=True)
class ActionItem:
    key: str
    title: str
    detail: str
    severity: ActionSeverity
    source: str
    panel_kind: str = "generic"
    """reduce | execute | checklist | data | swap | generic"""
    payload: Mapping[str, Any] = field(default_factory=dict)


def build_action_queue(
    *,
    entry_eval: EntryEvaluation,
    exit_eval: ExitEvaluation,
    swap_eval: SwapObserveEvaluation,
    stale_sources: list[SourceStatus],
    pending_executions: list[str] | None = None,
    cap_over_holdings: list[tuple[str, str, float, float]] | None = None,
    pre_launch: bool = False,
    checklist_blocking: list[Any] | None = None,
    window_end: date | None = None,
    pending_rescores: list[dict[str, Any]] | None = None,
) -> list[ActionItem]:
    if pre_launch:
        items: list[ActionItem] = []
        for item in checklist_blocking or []:
            items.append(
                ActionItem(
                    key=f"check_{item.key}",
                    title=item.title,
                    detail=action_sentence(
                        "checklist_item",
                        title=item.title,
                        why=item.why,
                        todo=item.todo,
                    ),
                    severity=ActionSeverity.WARN,
                    source="checklist",
                    panel_kind="checklist",
                    payload={"check_key": item.key, "todo": item.todo, "why": item.why},
                )
            )
        # Still surface rescore reviews in pre-launch (CECS work continues)
        items.extend(_rescore_items(pending_rescores))
        return _dedupe(items)

    items: list[ActionItem] = []

    # §5 window_end — wind-down at top of queue
    past_end = False
    if window_end is not None and getattr(exit_eval, "as_of", None) is not None:
        past_end = exit_eval.as_of >= window_end
    if past_end or getattr(exit_eval, "window_end_report", None):
        end_s = window_end.isoformat() if window_end else str(getattr(exit_eval, "as_of", ""))
        items.append(
            ActionItem(
                key="window_end_wind_down",
                title="논지 창 종료 — 정리 판정",
                detail=action_sentence("window_end_wind_down", date=end_s),
                severity=ActionSeverity.DANGER,
                source="exit",
                panel_kind="generic",
                payload={"report": getattr(exit_eval, "window_end_report", None)},
            )
        )

    items.extend(_rescore_items(pending_rescores))

    for act in exit_eval.actions:
        if act.action_type.value in {"REDUCE", "LIQUIDATE"}:
            why = str(act.detail or act.reason.value)
            items.append(
                ActionItem(
                    key=f"exit_{act.ticker}",
                    title=f"Exit 감축 — {act.ticker}",
                    detail=action_sentence("exit_reduce", why=why),
                    severity=ActionSeverity.DANGER,
                    source="exit",
                    panel_kind="reduce",
                    payload={"ticker": act.ticker, "why": why},
                )
            )
        elif "warn" in act.action_type.value.lower():
            why = str(act.detail or act.reason.value)
            items.append(
                ActionItem(
                    key=f"exit_warn_{act.ticker}",
                    title=f"Exit 경고 — {act.ticker}",
                    detail=action_sentence("exit_reduce", why=why),
                    severity=ActionSeverity.WARN,
                    source="exit",
                    panel_kind="reduce",
                    payload={"ticker": act.ticker, "why": why},
                )
            )

    for ticker, name, weight_pct, cap_pct in cap_over_holdings or []:
        items.append(
            ActionItem(
                key=f"cap_{ticker}",
                title=f"cap 감축 — {name}",
                detail=action_sentence(
                    "cap_reduce", cap=f"{cap_pct:.0f}", weight=f"{weight_pct:.1f}"
                ),
                severity=ActionSeverity.DANGER,
                source="sizing",
                panel_kind="reduce",
                payload={
                    "ticker": ticker,
                    "name": name,
                    "weight_pct": weight_pct,
                    "cap_pct": cap_pct,
                },
            )
        )

    for cand in swap_eval.candidates:
        why = (
            f"{cand.candidate_ticker}가 보유 {cand.held_ticker}보다 "
            f"{cand.score_gap_pct:.1f}% 높음 ({cand.consecutive_hits}회)"
        )
        items.append(
            ActionItem(
                key=f"swap_{cand.held_ticker}_{cand.candidate_ticker}",
                title="스왑 후보 (관찰)",
                detail=action_sentence("swap_observe", why=why),
                severity=ActionSeverity.INFO,
                source="swap",
                panel_kind="swap",
                payload={
                    "held": cand.held_ticker,
                    "candidate": cand.candidate_ticker,
                    "gap_pct": round(cand.score_gap_pct, 2),
                    "hits": cand.consecutive_hits,
                    "held_score": cand.held_score,
                    "cand_score": cand.candidate_score,
                },
            )
        )

    for st in entry_eval.statuses:
        tid = st.tranche_id.value if hasattr(st.tranche_id, "value") else str(st.tranche_id)
        label = format_tranche_label(tid)
        judgment = explain_tranche(st, pre_launch=False)
        if st.state in (TrancheState.READY, TrancheState.PARTIAL_EXECUTED) and st.trigger_met:
            items.append(
                ActionItem(
                    key=f"tranche_{tid}",
                    title=f"집행 대기 — {label}",
                    detail=action_sentence(
                        "tranche_ready", name=label, why=judgment.headline
                    ),
                    severity=ActionSeverity.WARN,
                    source="entry",
                    panel_kind="execute",
                    payload={"tranche_id": tid},
                )
            )
        for act in entry_eval.actions:
            if act.tranche_id == st.tranche_id and act.action_type == EntryActionType.EXECUTE:
                if not act.blocked:
                    items.append(
                        ActionItem(
                            key=f"exec_{tid}",
                            title=f"집행 신호 — {label}",
                            detail=action_sentence(
                                "tranche_ready", name=label, why=judgment.headline
                            ),
                            severity=ActionSeverity.WARN,
                            source="entry",
                            panel_kind="execute",
                            payload={"tranche_id": tid},
                        )
                    )

    for line in pending_executions or []:
        items.append(
            ActionItem(
                key=f"pending_{hash(line) % 10**8}",
                title="집행 대기",
                detail=str(line),
                severity=ActionSeverity.WARN,
                source="runtime",
                panel_kind="execute",
                payload={"note": line},
            )
        )

    for src in stale_sources:
        why = f"{src.label} as_of {src.as_of} (권장 {src.recommended_days}일 초과)"
        items.append(
            ActionItem(
                key=f"stale_{src.key}",
                title="데이터 갱신 필요",
                detail=action_sentence("data_stale", why=why),
                severity=ActionSeverity.WARN,
                source="data",
                panel_kind="data",
                payload={"source_key": src.key},
            )
        )

    return _dedupe(items)


def _rescore_items(pending_rescores: list[dict[str, Any]] | None) -> list[ActionItem]:
    out: list[ActionItem] = []
    for raw in pending_rescores or []:
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        out.append(
            ActionItem(
                key=key,
                title=str(raw.get("title") or "재채점 검토 필요"),
                detail=str(raw.get("detail") or ""),
                severity=ActionSeverity.WARN,
                source=str(raw.get("source") or "rescore"),
                panel_kind="rescore",
                payload={
                    "triggers": list(raw.get("triggers") or []),
                    "tickers": list(raw.get("tickers") or []),
                    "as_of": raw.get("as_of"),
                    "deep_link": "approval",
                },
            )
        )
    return out


def _dedupe(items: list[ActionItem]) -> list[ActionItem]:
    seen: set[str] = set()
    out: list[ActionItem] = []
    for it in items:
        if it.key in seen:
            continue
        seen.add(it.key)
        out.append(it)
    return out
