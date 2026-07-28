"""CECS(촉매 실행확실성) 프로필 및 티어 매핑."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class CatalystTier(str, Enum):
    CORE = "CORE"
    NEAR = "NEAR"
    SATELLITE = "SATELLITE"
    HEDGE = "HEDGE"
    EXCLUDE = "EXCLUDE"  # CECS < satellite_min — 배분 제외(명세: 풀에서 제외 권장)


@dataclass
class StockCatalystProfile:
    ticker: str
    name: str
    # alpha_portfolio 6-팩터 엔진: composite_score (spec의 factor_score_total에 대응)
    factor_score_total: float
    disclosure_status: float = 0.5
    execution_continuity: float = 0.5
    pension_flow_score: float = 0.5
    investment_purpose_flag: float = 0.5
    independent_catalyst_flag: float = 0.5
    policy_dependency_flag: float = 0.5
    manual_tier_override: Optional[CatalystTier] = None


def load_tier_weighting_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "cecs_weights": dict(cfg.get("cecs_weights") or {}),
        "policy_dependency_penalty_weight": float(cfg.get("policy_dependency_penalty_weight", 0.15)),
        "tier_thresholds": dict(cfg.get("tier_thresholds") or {}),
        "tier_target_weight": {
            CatalystTier(k): tuple(v) for k, v in (cfg.get("tier_target_weight") or {}).items()
        },
        "portfolio_guards": dict(cfg.get("portfolio_guards") or {}),
        "hedge_candidate": dict(cfg.get("hedge_candidate") or {}),
        "defaults": dict(cfg.get("defaults") or {}),
    }


def calculate_cecs(
    profile: StockCatalystProfile,
    *,
    weights: dict[str, float] | None = None,
    policy_penalty_weight: float = 0.15,
) -> float:
    w = weights or {
        "disclosure_status": 0.30,
        "execution_continuity": 0.20,
        "pension_flow_score": 0.15,
        "investment_purpose_flag": 0.15,
        "independent_catalyst_flag": 0.20,
    }
    base_score = (
        profile.disclosure_status * w["disclosure_status"]
        + profile.execution_continuity * w["execution_continuity"]
        + profile.pension_flow_score * w["pension_flow_score"]
        + profile.investment_purpose_flag * w["investment_purpose_flag"]
        + profile.independent_catalyst_flag * w["independent_catalyst_flag"]
    )
    penalty = profile.policy_dependency_flag * policy_penalty_weight
    score = max(0.0, base_score - penalty)
    return round(score * 100, 2)


def assign_catalyst_tier(
    cecs: float,
    *,
    is_hedge_candidate: bool = False,
    manual_override: CatalystTier | None = None,
    thresholds: dict[str, float] | None = None,
) -> CatalystTier:
    if manual_override is not None:
        return manual_override
    if is_hedge_candidate:
        return CatalystTier.HEDGE
    th = thresholds or {}
    core_min = float(th.get("core_min", 75))
    near_min = float(th.get("near_min", 55))
    satellite_min = float(th.get("satellite_min", 35))
    if cecs >= core_min:
        return CatalystTier.CORE
    if cecs >= near_min:
        return CatalystTier.NEAR
    if cecs >= satellite_min:
        return CatalystTier.SATELLITE
    return CatalystTier.EXCLUDE
