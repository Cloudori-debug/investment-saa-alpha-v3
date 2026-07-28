"""Pydantic config schema — confirmed values enforced; [TODO] fields optional/null."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TriggerType(str, Enum):
    TIME = "time"
    EVENT = "event"
    PRICE = "price"
    HYBRID = "hybrid"


class TrancheId(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


TRANCHE_ORDER: tuple[TrancheId, ...] = (
    TrancheId.T1,
    TrancheId.T2,
    TrancheId.T3,
    TrancheId.T4,
)


class ThesisWindowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = ""
    window_end: date

    @field_validator("window_end", mode="before")
    @classmethod
    def _parse_date(cls, value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return date.fromisoformat(str(value))


class CapitalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_fraction_of_total_assets: float = Field(..., gt=0.0, le=1.0)

    @field_validator("max_fraction_of_total_assets")
    @classmethod
    def _must_be_thirty_pct(cls, value: float) -> float:
        # 확정: 총자산 대비 30% 한도 — 임의 변경 방지
        if abs(value - 0.30) > 1e-9:
            raise ValueError(
                "capital.max_fraction_of_total_assets is locked at 0.30 "
                "(confirmed policy). Do not change without explicit decision."
            )
        return value


class TrancheConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight: float = Field(..., gt=0.0, le=1.0)
    trigger_type: TriggerType
    description: str = ""
    display_name: str = ""
    short_desc: str = ""
    event_ids: list[str] = Field(default_factory=list)
    # Former CECS score inputs remapped as T2 candidate sources (not auto-triggers)
    event_candidate_sources: list[str] = Field(default_factory=list)
    valuation_band: Optional[dict[str, Any]] = None
    hybrid_rules: Optional[dict[str, Any]] = None


class HardRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sunset_enabled: bool = True
    reverse_execution_blocked: bool = True
    thesis_damage_freeze_enabled: bool = True


class UniverseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Confirmed B안 (2026-07-16): shareholder_return_broad
    boundary_mode: Optional[Literal["financial", "shareholder_return_broad"]] = None
    include_markets: list[str] = Field(default_factory=lambda: ["KOSPI"])
    gate_config_path: str = "data/universe_filter.yaml"
    # Explicit: no financial-industry-only filter under B안
    financial_only_filter: bool = False

    @model_validator(mode="after")
    def _b_mode_locks(self) -> UniverseConfig:
        if self.boundary_mode == "shareholder_return_broad" and self.financial_only_filter:
            raise ValueError(
                "universe.financial_only_filter must be false when "
                "boundary_mode=shareholder_return_broad (B안)."
            )
        if self.boundary_mode == "shareholder_return_broad":
            markets = [str(m).upper() for m in self.include_markets]
            if markets != ["KOSPI"]:
                raise ValueError(
                    "universe.include_markets is locked to [KOSPI] under B안 "
                    "(+ universe_filter.yaml Gate). Got "
                    f"{self.include_markets}."
                )
        return self


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_cutoff: Optional[float] = None
    rescore_triggers: list[str] = Field(default_factory=list)


class SizingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Confirmed operating band (§7.5): review range 5~8, default policy 6.
    # Not unlocked to 30 — theme correlation means more names ≠ less thesis risk.
    target_names: int = Field(..., ge=5, le=8)
    initial_weight_cap: float = Field(..., gt=0.0, le=1.0)
    market_value_cap: float = Field(..., gt=0.0, le=1.0)
    # Post-cutoff concentration: max names per normalized sector_group.
    max_names_per_sector: int = Field(2, ge=1, le=8)
    # When 2+ names share a sector bucket, sum of weights ≤ this (sleeve-relative).
    sector_weight_cap: float = Field(0.35, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _lock_confirmed_sizing(self) -> SizingConfig:
        if abs(self.initial_weight_cap - 0.25) > 1e-9:
            raise ValueError(
                "sizing.initial_weight_cap is locked at 0.25 (confirmed)."
            )
        if abs(self.market_value_cap - 0.35) > 1e-9:
            raise ValueError(
                "sizing.market_value_cap is locked at 0.35 (confirmed)."
            )
        if abs(self.sector_weight_cap - 0.35) > 1e-9:
            raise ValueError(
                "sizing.sector_weight_cap is locked at 0.35 (confirmed)."
            )
        if self.market_value_cap + 1e-9 < self.initial_weight_cap:
            raise ValueError(
                "market_value_cap must be >= initial_weight_cap"
            )
        return self


class ExitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thesis_damage_exit: Optional[dict[str, Any]] = None
    score_below_cutoff_action: Optional[Literal["liquidate", "reduce"]] = None
    target_valuation_exit: Optional[dict[str, Any]] = None
    window_end_portfolio_action: Optional[dict[str, Any]] = None
    # Confirmed: block new entry without per-name target valuation on file
    entry_require_target_valuation: bool = True
    target_valuation_modify: Optional[dict[str, Any]] = None


class SwapRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["observe_only", "active"] = "observe_only"
    score_gap_pct: float = Field(default=20.0, ge=0.0)
    consecutive_hits: int = Field(default=2, ge=1)


class ThesisBackgroundConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basel3_excluded_from_t2: bool = True
    basel3_note: str = ""


class AlphaSystemConfig(BaseModel):
    """Root config. Confirmed locks + [TODO] nulls."""

    model_config = ConfigDict(extra="forbid")

    version: str
    purpose: str = "absolute_return_catalyst_bet"
    thesis_window: ThesisWindowConfig
    capital: CapitalConfig
    tranches: dict[str, TrancheConfig]
    hard_rules: HardRulesConfig
    thesis_damage_event_ids: list[str] = Field(default_factory=list)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    sizing: SizingConfig = Field(default_factory=SizingConfig)
    exit: ExitConfig = Field(default_factory=ExitConfig)
    benchmark: Optional[str] = None
    # T4 12-month rule anchor
    go_live_date: Optional[date] = None
    swap_rule: SwapRuleConfig = Field(default_factory=SwapRuleConfig)
    thesis_background: ThesisBackgroundConfig = Field(
        default_factory=ThesisBackgroundConfig
    )

    @field_validator("go_live_date", mode="before")
    @classmethod
    def _parse_go_live(cls, value: Any) -> Optional[date]:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return date.fromisoformat(str(value))

    @model_validator(mode="after")
    def _validate_tranches(self) -> AlphaSystemConfig:
        expected = {t.value for t in TRANCHE_ORDER}
        keys = set(self.tranches.keys())
        if keys != expected:
            raise ValueError(
                f"tranches must be exactly {sorted(expected)}, got {sorted(keys)}"
            )
        weights = [self.tranches[t.value].weight for t in TRANCHE_ORDER]
        if any(abs(w - 0.25) > 1e-9 for w in weights):
            raise ValueError(
                "each tranche weight is locked at 0.25 (4-way equal split)."
            )
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("tranche weights must sum to 1.0")

        type_map = {
            TrancheId.T1: TriggerType.TIME,
            TrancheId.T2: TriggerType.EVENT,
            TrancheId.T3: TriggerType.PRICE,
            TrancheId.T4: TriggerType.HYBRID,
        }
        for tid, expected_type in type_map.items():
            actual = self.tranches[tid.value].trigger_type
            if actual != expected_type:
                raise ValueError(
                    f"{tid.value}.trigger_type must be {expected_type.value}, "
                    f"got {actual.value}"
                )
        return self

    def todo_fields(self) -> list[str]:
        """Unset [TODO] knobs — structure present, values deferred."""
        pending: list[str] = []
        if not self.thesis_damage_event_ids:
            pending.append("thesis_damage_event_ids")
        if self.scoring.score_cutoff is None:
            pending.append("scoring.score_cutoff")
        if self.exit.thesis_damage_exit is None:
            pending.append("exit.thesis_damage_exit")
        if self.exit.score_below_cutoff_action is None:
            pending.append("exit.score_below_cutoff_action")
        if self.exit.target_valuation_exit is None:
            pending.append("exit.target_valuation_exit")
        if self.exit.window_end_portfolio_action is None:
            pending.append("exit.window_end_portfolio_action")
        if self.go_live_date is None:
            pending.append("go_live_date")
        # Confirmed trigger package (2026-07-16) — not TODO:
        # T2 event_ids, T3 valuation_band, T4 hybrid_rules, rescore_triggers
        return pending

    def require(self, field_path: str) -> None:
        """Raise if a [TODO] field needed for the requested feature is unset."""
        if field_path in self.todo_fields():
            raise ConfigTodoError(
                f"[TODO] config field unset: {field_path}. "
                "Fill alpha_system/config before using this feature."
            )


class ConfigTodoError(ValueError):
    """Raised when code path needs a user-pending [TODO] config value."""
