from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

SCHEMA_VERSION = "1.0"

P0_LIMITATIONS = [
    "VIX=글로벌 리스크 프록시 (VKOSPI·한국 고유 리스크 미반영)",
    "시장가격 기반 국면 (Tier2 매크로 미포함)",
]


class MarketPhase(str, Enum):
    MARKET_RECOVERY = "MARKET_RECOVERY"
    MARKET_EXPANSION = "MARKET_EXPANSION"
    MARKET_SLOWDOWN = "MARKET_SLOWDOWN"
    MARKET_CONTRACTION = "MARKET_CONTRACTION"
    UNKNOWN = "UNKNOWN"


# backward compatibility alias
EconomicPhase = MarketPhase

# legacy enum value mapping
LEGACY_PHASE_MAP: dict[str, MarketPhase] = {
    "RECOVERY": MarketPhase.MARKET_RECOVERY,
    "EXPANSION": MarketPhase.MARKET_EXPANSION,
    "SLOWDOWN": MarketPhase.MARKET_SLOWDOWN,
    "CONTRACTION": MarketPhase.MARKET_CONTRACTION,
    "UNKNOWN": MarketPhase.UNKNOWN,
}


class RiskRegime(str, Enum):
    RISK_ON = "RISK_ON"
    YELLOW_STABLE = "YELLOW_STABLE"
    CAUTION = "CAUTION"
    RISK_OFF = "RISK_OFF"
    CRISIS = "CRISIS"


CompassDirection = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
GroupActionType = Literal[
    "Buy",
    "BuyCandidate",
    "WaitTrigger",
    "Hold",
    "Trim",
    "Park",
    "NoTrade",
    "Wait",
]


class CompassSignal(BaseModel):
    key: str
    label: str
    score: float = Field(ge=-1, le=1)
    detail: str


class ScoreBreakdownItem(BaseModel):
    axis: str
    indicator: str
    contribution: float
    detail: str = ""


class OverrideInfo(BaseModel):
    active: bool = False
    reason: str | None = None
    timestamp: str | None = None


class CompassResult(BaseModel):
    date: str
    market_phase: MarketPhase  # applied (hysteresis-confirmed) phase used for tilts
    phase_confidence: float = Field(ge=0, le=1)
    computed_market_phase: MarketPhase | None = None  # raw same-day phase before hysteresis
    computed_regime: RiskRegime
    regime_confidence: float = Field(ge=0, le=1)
    compass_direction: CompassDirection
    compass_summary: str
    growth_score: float = Field(ge=-1, le=1)
    inflation_score: float = Field(ge=-1, le=1)
    liquidity_score: float = Field(ge=-1, le=1)
    risk_appetite_score: float = Field(ge=-1, le=1)
    signals: list[CompassSignal]
    score_breakdown: list[ScoreBreakdownItem]
    manual_regime: str | None = None
    applied_regime: RiskRegime
    override: OverrideInfo = Field(default_factory=OverrideInfo)
    data_gate: str = "GREEN"
    execution_level: int = 1
    hysteresis_note: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def economic_phase(self) -> MarketPhase:
        """Deprecated alias for market_phase."""
        return self.market_phase

    @computed_field  # type: ignore[prop-decorator]
    @property
    def risk_regime(self) -> RiskRegime:
        """Deprecated alias for computed_regime."""
        return self.computed_regime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_regime(self) -> RiskRegime:
        """Deprecated alias for applied_regime."""
        return self.applied_regime


class GroupAllocation(BaseModel):
    asset_group: str
    saa_weight: float
    phase_tilt: float
    regime_tilt: float
    raw_target: float
    final_target: float
    min_weight: float
    max_weight: float

    @computed_field  # type: ignore[prop-decorator]
    @property
    def taa_tilt(self) -> float:
        return round(self.phase_tilt + self.regime_tilt, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_weight(self) -> float:
        return self.final_target


class PortfolioAllocation(BaseModel):
    profile: str
    market_phase: MarketPhase
    applied_regime: RiskRegime
    compass_direction: CompassDirection
    groups: list[GroupAllocation]
    total_weight: float
    notes: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def economic_phase(self) -> MarketPhase:
        return self.market_phase

    @computed_field  # type: ignore[prop-decorator]
    @property
    def risk_regime(self) -> RiskRegime:
        return self.applied_regime


class GroupGapRow(BaseModel):
    asset_group: str
    current: float
    target: float
    gap: float
    action: GroupActionType
    reason: str


class TargetMismatchWarning(BaseModel):
    asset_group: str
    ticker_target_sum: float
    allocation_target: float
    diff: float

