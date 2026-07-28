"""Entry module — tranche state machine + hard rules."""

from __future__ import annotations

from alpha_system.entry.entry_gates import check_entry_target_valuation
from alpha_system.entry.evaluate import (
    EntryEvaluation,
    TriggerSnapshot,
    attempt_execute,
    evaluate_entry,
)
from alpha_system.entry.models import (
    EntryAction,
    EntryActionType,
    TrancheState,
    TrancheStatus,
)

__all__ = [
    "EntryAction",
    "EntryActionType",
    "EntryEvaluation",
    "TrancheState",
    "TrancheStatus",
    "TriggerSnapshot",
    "attempt_execute",
    "check_entry_target_valuation",
    "evaluate_entry",
]
