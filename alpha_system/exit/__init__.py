"""Exit module — liquidate/reduce judgments; discretionary exit warned but allowed."""

from __future__ import annotations

from alpha_system.exit.evaluate import (
    ExitEvaluation,
    ExitSnapshot,
    PositionView,
    attempt_exit,
    evaluate_exits,
)
from alpha_system.exit.models import ExitAction, ExitActionType, ExitReason
from alpha_system.exit.target_valuation import (
    TargetValuationModifyResult,
    modify_target_valuation,
)

__all__ = [
    "ExitAction",
    "ExitActionType",
    "ExitEvaluation",
    "ExitReason",
    "ExitSnapshot",
    "PositionView",
    "TargetValuationModifyResult",
    "attempt_exit",
    "evaluate_exits",
    "modify_target_valuation",
]
