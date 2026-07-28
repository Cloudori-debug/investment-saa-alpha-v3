from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.catalyst_profile import CatalystTier, StockCatalystProfile, assign_catalyst_tier, calculate_cecs
from src.tier_allocator import allocate_weights, build_tiered_portfolio


def _profile(score: float, **kwargs: float) -> StockCatalystProfile:
    return StockCatalystProfile(
        ticker="000001",
        name="테스트",
        factor_score_total=score,
        disclosure_status=kwargs.get("disclosure_status", 0.5),
        execution_continuity=kwargs.get("execution_continuity", 0.5),
        pension_flow_score=kwargs.get("pension_flow_score", 0.5),
        investment_purpose_flag=kwargs.get("investment_purpose_flag", 0.5),
        independent_catalyst_flag=kwargs.get("independent_catalyst_flag", 0.5),
        policy_dependency_flag=kwargs.get("policy_dependency_flag", 0.0),
    )


def test_calculate_cecs_penalty() -> None:
    high = _profile(70.0, disclosure_status=1.0, policy_dependency_flag=0.0)
    low = _profile(70.0, disclosure_status=1.0, policy_dependency_flag=1.0)
    assert calculate_cecs(high) > calculate_cecs(low)


def test_assign_catalyst_tier_hedge_override() -> None:
    assert assign_catalyst_tier(20.0, is_hedge_candidate=True) == CatalystTier.HEDGE
    assert assign_catalyst_tier(80.0, is_hedge_candidate=False) == CatalystTier.CORE
    assert assign_catalyst_tier(40.0, is_hedge_candidate=False) == CatalystTier.SATELLITE
    assert assign_catalyst_tier(10.0, is_hedge_candidate=False) == CatalystTier.EXCLUDE


def test_allocate_weights_sums_to_one() -> None:
    profiles_with_tier = [
        (StockCatalystProfile("111111", "C1", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111112", "C2", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("222221", "N1", 60.0), CatalystTier.NEAR),
        (StockCatalystProfile("222222", "N2", 60.0), CatalystTier.NEAR),
        (StockCatalystProfile("333331", "S1", 55.0), CatalystTier.SATELLITE),
        (StockCatalystProfile("333332", "S2", 55.0), CatalystTier.SATELLITE),
        (StockCatalystProfile("444441", "H1", 50.0), CatalystTier.HEDGE),
    ]
    weights = allocate_weights(profiles_with_tier)
    assert abs(sum(weights.values()) - 1.0) < 0.01


def test_build_tiered_portfolio_uses_composite_score_field() -> None:
    p = StockCatalystProfile("005930", "삼성", factor_score_total=72.0, disclosure_status=0.9)
    out = build_tiered_portfolio([p], set(), tw_cfg={})
    assert out["005930"]["composite_score"] == 72.0
    assert out["005930"]["factor_score_total"] == 72.0
    assert abs(out["005930"]["weight"] - 1.0) < 0.01


def test_profile_from_scores_row_maps_composite_score(tmp_path: Path) -> None:
    from src.tier_allocator import profile_from_scores_row

    row = pd.Series({"ticker": "123456", "name": "X", "composite_score": 61.5})
    prof = profile_from_scores_row(row)
    assert prof.factor_score_total == 61.5


def test_allocate_weights_respects_single_name_max_after_normalize() -> None:
    """7종목 기본 구성(2+2+2+1)에서 18% 상한 유지."""
    profiles_with_tier = [
        (StockCatalystProfile("111111", "C1", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111112", "C2", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("222221", "N1", 60.0), CatalystTier.NEAR),
        (StockCatalystProfile("222222", "N2", 60.0), CatalystTier.NEAR),
        (StockCatalystProfile("333331", "S1", 55.0), CatalystTier.SATELLITE),
        (StockCatalystProfile("333332", "S2", 55.0), CatalystTier.SATELLITE),
        (StockCatalystProfile("444441", "H1", 50.0), CatalystTier.HEDGE),
    ]
    weights = allocate_weights(profiles_with_tier, single_name_max=0.18)
    assert abs(sum(weights.values()) - 1.0) < 0.01
    assert max(weights.values()) <= 0.18 + 1e-6


def test_allocate_weights_three_core_cap_saturation_under_allocates() -> None:
    """동일 티어(CORE) 3종 집중 — cap 포화 시 합계 100% 미달."""
    profiles_with_tier = [
        (StockCatalystProfile("111111", "C1", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111112", "C2", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111113", "C3", 70.0), CatalystTier.CORE),
    ]
    weights = allocate_weights(profiles_with_tier, single_name_max=0.18)
    assert abs(sum(weights.values()) - 0.54) < 0.01
    assert max(weights.values()) <= 0.18 + 1e-6


def test_allocate_weights_four_core_one_hedge_cap_saturation() -> None:
    """CORE 4 + HEDGE 1 — receiver headroom 부족 시 합계 100% 미달."""
    profiles_with_tier = [
        (StockCatalystProfile("111111", "C1", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111112", "C2", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111113", "C3", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("111114", "C4", 70.0), CatalystTier.CORE),
        (StockCatalystProfile("444441", "H1", 50.0), CatalystTier.HEDGE),
    ]
    weights = allocate_weights(profiles_with_tier, single_name_max=0.18)
    assert abs(sum(weights.values()) - 0.90) < 0.01
    assert max(weights.values()) <= 0.18 + 1e-6


def test_build_tiered_portfolio_meta_under_allocation() -> None:
    profiles = [
        StockCatalystProfile("111111", "C1", 70.0, disclosure_status=0.9),
        StockCatalystProfile("111112", "C2", 70.0, disclosure_status=0.9),
        StockCatalystProfile("111113", "C3", 70.0, disclosure_status=0.9),
    ]
    out = build_tiered_portfolio(profiles, set(), tw_cfg={})
    meta = out["_meta"]
    assert meta["allocation_complete"] is False
    assert abs(meta["allocation_weight_sum"] - 0.54) < 0.02
    assert any("100% 미달" in w for w in meta["warnings"])
