"""Exit action / reason models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


class ExitReason(str, Enum):
    THESIS_DAMAGE = "thesis_damage"  # held position — distinct from entry FROZEN
    SCORE_BELOW_CUTOFF = "score_below_cutoff"
    TARGET_VALUATION = "target_valuation"
    WINDOW_END = "window_end"
    MARKET_VALUE_CAP = "market_value_cap"  # sizing boundary: exit-only detect
    DISCRETIONARY = "discretionary"  # user override — warn, do not block


class ExitActionType(str, Enum):
    LIQUIDATE = "LIQUIDATE"
    REDUCE = "REDUCE"
    PORTFOLIO_WIND_DOWN_REPORT = "PORTFOLIO_WIND_DOWN_REPORT"
    WARN_DISCRETIONARY = "WARN_DISCRETIONARY"


@dataclass(frozen=True)
class ExitAction:
    action_type: ExitActionType
    reason: ExitReason
    ticker: str
    as_of: date
    detail: str
    fraction: float = 1.0  # 1.0 = full liquidate; <1 reduce
    rule_met: bool = True
    blocked: bool = False  # always False for exits (asymmetric vs entry)
    meta: dict[str, Any] = field(default_factory=dict)
    journal_id: Optional[str] = None
