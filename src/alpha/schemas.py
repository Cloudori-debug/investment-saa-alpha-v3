from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.field_normalize import normalize_sector

ALPHA_SCHEMA_VERSION = "1.0"

Grade = Literal["A", "B", "C", "Reject"]
EligibleAction = Literal["BUY_CANDIDATE", "WATCH", "HOLD", "NO_NEW"]
ReviewAction = Literal["KEEP", "WATCH", "TRIM", "REPLACE_CANDIDATE"]


class UniverseRecord(BaseModel):
    ticker: str
    name: str
    market: str = "KOSPI"
    security_type: str = "common_stock"
    sector: str = ""
    industry: str = ""
    listed_date: str = ""
    is_preferred: bool = False
    is_etf_etn: bool = False
    is_reit: bool = False
    is_spac: bool = False
    is_trading_halt: bool = False
    is_administrative_issue: bool = False
    audit_opinion: str = "clean"
    capital_impairment: bool = False

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_sector_field(cls, v: Any) -> str:
        return normalize_sector(v)


class FundamentalRecord(BaseModel):
    ticker: str
    period_end: str = ""
    report_date: str = ""
    usable_from_date: str = ""
    roe: float | None = None
    roa: float | None = None
    operating_margin: float | None = None
    gross_profitability: float | None = None
    debt_ratio: float | None = None
    interest_coverage: float | None = None
    per: float | None = None
    pbr: float | None = None
    pcr: float | None = None
    psr: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    fcf: float | None = None
    operating_cash_flow: float | None = None
    net_income: float | None = None
    earnings_yoy: float | None = None


class PriceRecord(BaseModel):
    date: str
    ticker: str
    close: float = 0
    market_cap: float = 0
    trading_value_20d: float = 0
    trading_value_60d: float = 0
    return_1m: float = 0
    return_3m: float = 0
    return_6m: float = 0
    return_12m: float = 0
    return_12m_ex_1m: float = 0
    high_52w: float = 0
    distance_from_52w_high: float = 0
    volatility_60d: float = 0


class ExcludedRecord(BaseModel):
    ticker: str
    name: str
    exclude_reason: str
    failed_rule: str


def make_excluded(ticker: str, name: str, reason: str, rule: str) -> ExcludedRecord:
    return ExcludedRecord(
        ticker=ticker,
        name=name,
        exclude_reason=reason,
        failed_rule=rule,
    )


class AlphaCandidate(BaseModel):
    rank: int
    ticker: str
    name: str
    sector: str
    quality_score: float
    valuation_score: float
    momentum_score: float
    shareholder_return_score: float = 0.0
    base_score: float
    penalty: float
    total_score: float
    grade: Grade
    key_reason: str
    eligible_action: EligibleAction

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_sector_field(cls, v: Any) -> str:
        return normalize_sector(v)


class HoldingReview(BaseModel):
    ticker: str
    name: str
    current_weight: float
    target_weight: float
    alpha_score: float
    grade: Grade
    review_action: ReviewAction
    reason: str


class AlphaPipelineResult(BaseModel):
    as_of: str
    candidates: list[AlphaCandidate]
    excluded: list[ExcludedRecord]
    holdings_review: list[HoldingReview]
    data_gate: str
    limitations: list[str]
