"""Tranche / action models for the entry state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from alpha_system.schema import TrancheId, TriggerType


class TrancheState(str, Enum):
    """Entry lifecycle for one tranche."""

    PENDING = "PENDING"  # waiting for trigger
    READY = "READY"  # trigger met; execution action may be reported
    PARTIAL_EXECUTED = "PARTIAL_EXECUTED"  # T4 split: initial slice done, remainder pending
    EXECUTED = "EXECUTED"  # execution acknowledged
    EXPIRED = "EXPIRED"  # window_end sunset → SAA reflux
    FROZEN = "FROZEN"  # thesis-damage freeze → reflux


class EntryActionType(str, Enum):
    MARK_READY = "MARK_READY"
    EXECUTE = "EXECUTE"
    REFLUX_TO_SAA = "REFLUX_TO_SAA"
    FREEZE = "FREEZE"
    WARN_BLOCKED = "WARN_BLOCKED"


@dataclass(frozen=True)
class EntryAction:
    action_type: EntryActionType
    tranche_id: TrancheId
    reason: str
    weight: float
    as_of: date
    blocked: bool = False


@dataclass
class TrancheStatus:
    tranche_id: TrancheId
    state: TrancheState
    weight: float
    trigger_type: TriggerType
    trigger_met: bool
    detail: str = ""
    last_action: Optional[EntryAction] = None
    meta: dict = field(default_factory=dict)
