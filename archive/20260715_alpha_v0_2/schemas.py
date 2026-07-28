from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ALPHA_V02_SCHEMA = "0.2"
Classification = Literal[
    "Core",
    "Active",
    "Candidate",
    "Watch",
    "Legacy",
    "Exit",
    "Excluded",
]
NewBuyStatus = Literal["forbidden", "research_only", "allowed_if_budget"]
AlphaBudgetStatus = Literal["OK", "OVERWEIGHT", "UNDERWEIGHT"]


class GateResult(BaseModel):
    passed: bool
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    rel_return_90d: float | None = None
    rel_return_120d: float | None = None


class ScoredRow(BaseModel):
    ticker: str
    name: str
    sector: str = ""
    current_weight_pct: float = 0.0
    in_portfolio: bool = False
    in_legacy_target: bool = False
    legacy_screener_grade: str = ""
    legacy_screener_rank: int | None = None
    exclusion_pass: bool = True
    quality_pass: bool = False
    momentum_pass: bool = False
    quality_score: float = 0.0
    value_score: float = 0.0
    momentum_score: float = 0.0
    catalyst_score: float = 0.0
    risk_control_score: float = 0.0
    total_score: float = 0.0
    rel_return_90d: float | None = None
    rel_return_120d: float | None = None
    classification: Classification = "Excluded"
    new_buy_status: NewBuyStatus = "forbidden"
    reason: str = ""


class AlphaV02ShadowResult(BaseModel):
    schema_version: str = ALPHA_V02_SCHEMA
    mode: str = "shadow"
    execution_authority: str = "v1.0.2"
    as_of: str
    alpha_budget_status: AlphaBudgetStatus = "OK"
    current_alpha_weight_pct: float = 0.0
    new_alpha_buy_allowed: bool = False
    allowed_action: str = "hold_or_trim_only"
    rows: list[ScoredRow] = Field(default_factory=list)
    legacy_diff_count: int = 0
    benchmark_notes: list[str] = Field(default_factory=list)
