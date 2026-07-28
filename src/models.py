from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.field_normalize import normalize_sector


VALID_ASSET_GROUPS = frozenset({
    "cash_short_bond",
    "domestic_beta",
    "global_beta",
    "fx_dollar",
    "hedge_alt",
    "income_alt",
    "kr_alpha",
})

GapStatus = Literal[
    "Underweight",
    "Slightly underweight",
    "Within band",
    "Slightly overweight",
    "Overweight",
    "Not in target",
    "No position",
]

ActionType = Literal[
    "Buy-allowed",
    "Add",
    "Hold",
    "Wait",
    "Trim",
    "Park",
    "Replace",
    "Stop-buy",
    "Risk defense",
    "No trade",
    "Review-only",
]

DataGate = Literal["GREEN", "YELLOW", "RED"]


class PositionRow(BaseModel):
    ticker: str
    name: str
    asset_group: str
    sector: str = ""
    style: str = ""
    quantity: float | None = None
    current_value: float = Field(gt=0)
    avg_price: float | None = None
    current_price: float | None = None

    @field_validator("asset_group")
    @classmethod
    def validate_asset_group(cls, v: str) -> str:
        if v not in VALID_ASSET_GROUPS:
            raise ValueError(f"invalid asset_group: {v}")
        return v

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_sector_field(cls, v: Any) -> str:
        return normalize_sector(v)


class TargetRow(BaseModel):
    ticker: str
    name: str
    asset_group: str
    sector: str = ""
    role: str = ""
    target_weight: float = Field(ge=0, le=100)
    min_weight: float = Field(ge=0, le=100)
    max_weight: float = Field(ge=0, le=100)

    @field_validator("asset_group")
    @classmethod
    def validate_asset_group(cls, v: str) -> str:
        if v not in VALID_ASSET_GROUPS:
            raise ValueError(f"invalid asset_group: {v}")
        return v

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_sector_field(cls, v: Any) -> str:
        return normalize_sector(v)


class MarketIndicators(BaseModel):
    date: str
    kospi: float = 0
    kospi_recent_high: float = 0
    kospi_200ma: float = 0
    sp500: float = 0
    sp500_recent_high: float = 0
    vix: float = 0
    usdkrw: float = 0
    korea_10y: float = 0
    oil_brent: float = 0
    gold: float = 0
    foreign_flow_3d: str = "neutral"
    regime: str = "NEUTRAL"
    regime_override_reason: str | None = None
    regime_set_date: str | None = None
    regime_expires_date: str | None = None


class GapRow(BaseModel):
    ticker: str
    name: str
    asset_group: str
    current_weight: float
    target_weight: float
    gap: float
    min_weight: float
    max_weight: float
    status: GapStatus
    in_target: bool


class TradeAction(BaseModel):
    ticker: str
    name: str
    action: ActionType
    reason: str
    allowed_size_pct: float
    priority: Literal["High", "Medium", "Low"]


class TriggerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    WATCH = "watch"
    RISK = "risk"


class TriggerAlert(BaseModel):
    key: str
    label: str
    status: TriggerStatus
    detail: str
