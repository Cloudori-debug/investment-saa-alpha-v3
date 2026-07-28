"""Korean judgment sentences from UI_COPY templates — never expose raw internal logs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from alpha_system.entry.models import TrancheState, TrancheStatus
from alpha_system.ui.services.ui_copy import copy_get, format_tranche_label, load_ui_copy


@dataclass(frozen=True)
class JudgmentSentence:
    headline: str
    """「시스템은 지금 이렇게 판단 중」본문."""
    next_check: str = ""
    raw_detail: str = ""
    """원문 — 접힌 상세에만."""
    mapped: bool = True


_KNOWN_DETAIL_PREFIXES = (
    "pre_launch",
    "already executed",
    "time: system_started",
    "time: system not started",
    "event:",
    "price:",
    "hybrid:",
    "t3:",
    "valuation",
    "unknown",
    "freeze",
    "thesis",
    "sunset",
    "expired",
    "ready",
    "PARTIAL",
)


def _state_key(state: TrancheState) -> Optional[str]:
    if state == TrancheState.EXECUTED:
        return "already_executed"
    if state == TrancheState.FROZEN:
        return "frozen"
    if state == TrancheState.EXPIRED:
        return "expired"
    if state == TrancheState.READY:
        return "ready_to_execute"
    if state == TrancheState.PARTIAL_EXECUTED:
        return "partial_executed"
    return None


def _is_data_unknown(detail: str, meta: dict[str, Any]) -> bool:
    d = (detail or "").lower()
    if meta.get("pre_launch"):
        return False
    if "unknown" in d or "missing" in d or "no data" in d or "이력" in d:
        return True
    if meta.get("data_missing") or meta.get("pbr_unknown"):
        return True
    return False


def explain_tranche(
    status: TrancheStatus,
    *,
    pre_launch: bool = False,
) -> JudgmentSentence:
    tid = status.tranche_id.value if hasattr(status.tranche_id, "value") else str(status.tranche_id)
    detail = status.detail or ""
    meta = dict(status.meta or {})

    if pre_launch or meta.get("pre_launch"):
        return JudgmentSentence(
            headline=copy_get("judgment", "pre_launch_locked"),
            raw_detail=detail,
            mapped=True,
        )

    state_key = _state_key(status.state)
    if state_key and status.state in {
        TrancheState.EXECUTED,
        TrancheState.FROZEN,
        TrancheState.EXPIRED,
    }:
        return JudgmentSentence(
            headline=copy_get("judgment", state_key),
            raw_detail=detail,
            mapped=True,
        )

    bucket = "unknown" if _is_data_unknown(detail, meta) else (
        "met" if status.trigger_met else "not_met"
    )
    # READY with trigger_met → ready sentence preferred
    if status.state == TrancheState.READY and status.trigger_met:
        headline = copy_get("judgment", "ready_to_execute")
        specific = copy_get("judgment", tid, "met", default="")
        if specific:
            headline = specific
        next_check = copy_get("judgment", "next_check", tid, default="")
        return JudgmentSentence(
            headline=headline,
            next_check=next_check,
            raw_detail=detail,
            mapped=True,
        )

    if status.state == TrancheState.PARTIAL_EXECUTED:
        return JudgmentSentence(
            headline=copy_get("judgment", "partial_executed"),
            next_check=copy_get("judgment", "next_check", tid, default=""),
            raw_detail=detail,
            mapped=True,
        )

    specific = copy_get("judgment", tid, bucket, default="")
    if specific:
        return JudgmentSentence(
            headline=specific,
            next_check=copy_get("judgment", "next_check", tid, default=""),
            raw_detail=detail,
            mapped=True,
        )

    # unmapped internal string
    return JudgmentSentence(
        headline=copy_get("judgment", "fallback", default="판정 사유 확인 필요"),
        next_check=copy_get("judgment", "next_check", tid, default=""),
        raw_detail=detail or "(empty)",
        mapped=False,
    )


def action_sentence(kind: str, **fmt: Any) -> str:
    return copy_get("action_queue", kind, default="", **fmt)
