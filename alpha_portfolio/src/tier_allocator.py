"""CECS 티어별 비중 배분 및 스코어링 엔진 연결.

참고: live target 산출 경로에는 연결되지 않은 별도 연구/실험 트랙이다.
운영 진실(위성 단일 종목 상한 등)은 alpha_portfolio/config/target_matrix.yaml 을 따른다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from src.catalyst_profile import (
    CatalystTier,
    StockCatalystProfile,
    assign_catalyst_tier,
    calculate_cecs,
    load_tier_weighting_config,
)


def is_hedge_candidate_row(row: pd.Series, hedge_cfg: dict[str, Any]) -> bool:
    min_sr = float(hedge_cfg.get("min_score_sr", 70))
    min_div = float(hedge_cfg.get("min_dividend_yield", 2.5))
    max_vol = float(hedge_cfg.get("max_volatility_1y", 30))
    sr = float(row.get("score_sr") or 0)
    div = row.get("dividend_yield")
    vol = row.get("volatility_1y")
    div_ok = div is not None and not pd.isna(div) and float(div) >= min_div
    vol_ok = vol is None or pd.isna(vol) or float(vol) <= max_vol
    return sr >= min_sr and div_ok and vol_ok


def profile_from_scores_row(
    row: pd.Series,
    *,
    neutral: float = 0.5,
    manual_tier: str | None = None,
) -> StockCatalystProfile:
    override = CatalystTier(manual_tier) if manual_tier else None
    return StockCatalystProfile(
        ticker=str(row.get("ticker", "")).zfill(6),
        name=str(row.get("name") or row.get("ticker", "")),
        factor_score_total=float(row.get("composite_score") or row.get("factor_score_total") or 0),
        disclosure_status=neutral,
        execution_continuity=neutral,
        pension_flow_score=neutral,
        investment_purpose_flag=neutral,
        independent_catalyst_flag=neutral,
        policy_dependency_flag=neutral,
        manual_tier_override=override,
    )


def allocate_weights(
    profiles_with_tier: list[tuple[StockCatalystProfile, CatalystTier]],
    *,
    tier_target_weight: dict[CatalystTier, tuple[float, float]] | None = None,
    single_name_min: float = 0.08,
    single_name_max: float = 0.18,
) -> dict[str, float]:
    """티어별 mid 비례 배분 후 합=1 정규화. single_name_max는 재정규화 후에도 유지."""
    allocatable = [(p, t) for p, t in profiles_with_tier if t != CatalystTier.EXCLUDE]
    if not allocatable:
        return {}
    if len(allocatable) == 1:
        return {allocatable[0][0].ticker: 1.0}

    targets = tier_target_weight or {
        CatalystTier.CORE: (0.15, 0.18),
        CatalystTier.NEAR: (0.10, 0.13),
        CatalystTier.SATELLITE: (0.08, 0.10),
        CatalystTier.HEDGE: (0.08, 0.10),
    }
    tier_groups: dict[CatalystTier, list[StockCatalystProfile]] = defaultdict(list)
    for profile, tier in allocatable:
        tier_groups[tier].append(profile)

    raw_weights: dict[str, float] = {}
    for tier, profiles in tier_groups.items():
        if tier not in targets:
            continue
        low, high = targets[tier]
        mid = (low + high) / 2
        total_factor = sum(p.factor_score_total for p in profiles) or 1.0
        for p in profiles:
            proportional = (p.factor_score_total / total_factor) * mid * len(profiles)
            raw_weights[p.ticker] = min(max(proportional, single_name_min), single_name_max)

    weights = dict(raw_weights)
    for _ in range(32):
        total = sum(weights.values()) or 1.0
        weights = {t: w / total for t, w in weights.items()}
        capped = {t: w for t, w in weights.items() if w > single_name_max + 1e-9}
        if not capped:
            break
        surplus = sum(w - single_name_max for w in capped.values())
        for t in capped:
            weights[t] = single_name_max
        receivers = [t for t, w in weights.items() if w < single_name_max - 1e-9]
        recv_total = sum(weights[t] for t in receivers)
        if not receivers or recv_total <= 0 or surplus <= 0:
            break
        for t in receivers:
            weights[t] += surplus * (weights[t] / recv_total)

    return {ticker: round(w, 4) for ticker, w in weights.items()}


def build_tiered_portfolio(
    profiles: list[StockCatalystProfile],
    hedge_candidates: set[str],
    *,
    tw_cfg: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    cfg = load_tier_weighting_config(tw_cfg or {})
    weights_cfg = cfg["cecs_weights"]
    penalty = cfg["policy_dependency_penalty_weight"]
    thresholds = cfg["tier_thresholds"]
    tier_targets = cfg["tier_target_weight"]
    guards = cfg["portfolio_guards"]

    profiles_with_tier: list[tuple[StockCatalystProfile, CatalystTier]] = []
    for p in profiles:
        cecs = calculate_cecs(p, weights=weights_cfg, policy_penalty_weight=penalty)
        tier = assign_catalyst_tier(
            cecs,
            is_hedge_candidate=p.ticker in hedge_candidates,
            manual_override=p.manual_tier_override,
            thresholds=thresholds,
        )
        profiles_with_tier.append((p, tier))

    weights = allocate_weights(
        profiles_with_tier,
        tier_target_weight=tier_targets,
        single_name_min=float(guards.get("single_name_min", 0.08)),
        single_name_max=float(guards.get("single_name_max", 0.18)),
    )

    result: dict[str, Any] = {}
    for p, tier in profiles_with_tier:
        cecs = calculate_cecs(p, weights=weights_cfg, policy_penalty_weight=penalty)
        result[p.ticker] = {
            "name": p.name,
            "tier": tier.value,
            "cecs": cecs,
            "factor_score_total": p.factor_score_total,
            "composite_score": p.factor_score_total,
            "weight": weights.get(p.ticker, 0.0),
            "excluded_from_allocation": tier == CatalystTier.EXCLUDE,
        }

    allocatable_sum = sum(
        item["weight"]
        for item in result.values()
        if isinstance(item, dict) and not item.get("excluded_from_allocation")
    )
    warnings = portfolio_allocation_warnings(result, tw_cfg=cfg if tw_cfg else {})
    result["_meta"] = {
        "allocation_weight_sum": round(allocatable_sum, 4),
        "unallocated_weight": round(max(0.0, 1.0 - allocatable_sum), 4),
        "allocation_complete": abs(allocatable_sum - 1.0) <= 1e-3,
        "warnings": warnings,
    }
    return result


def build_tiered_portfolio_from_candidates(
    candidates: pd.DataFrame,
    fundamentals: pd.DataFrame | None,
    *,
    tw_cfg: dict[str, Any],
    max_names: int = 7,
) -> dict[str, dict[str, Any]]:
    if candidates.empty:
        return {}
    cfg = load_tier_weighting_config(tw_cfg)
    neutral = float((cfg.get("defaults") or {}).get("cecs_input_neutral", 0.5))
    hedge_cfg = cfg["hedge_candidate"]

    fund_by = {}
    if fundamentals is not None and not fundamentals.empty:
        fund_by = {
            str(r["ticker"]).zfill(6): r.to_dict()
            for _, r in fundamentals.iterrows()
        }

    top = candidates.head(max_names)
    hedge_set: set[str] = set()
    profiles: list[StockCatalystProfile] = []
    for _, row in top.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        merged = dict(row)
        fund = fund_by.get(ticker)
        if fund is not None:
            for col in ("dividend_yield", "volatility_1y", "score_sr"):
                if col not in merged or pd.isna(merged.get(col)):
                    val = fund.get(col) if isinstance(fund, dict) else fund[col]
                    merged[col] = val
        merged_row = pd.Series(merged)
        if is_hedge_candidate_row(merged_row, hedge_cfg):
            hedge_set.add(ticker)
        profiles.append(profile_from_scores_row(merged_row, neutral=neutral))

    return build_tiered_portfolio(profiles, hedge_set, tw_cfg=tw_cfg)


def portfolio_allocation_warnings(
    allocation: dict[str, Any],
    *,
    tw_cfg: dict[str, Any],
) -> list[str]:
    holdings = {
        k: v for k, v in allocation.items()
        if k != "_meta" and isinstance(v, dict)
    }
    if not holdings:
        return ["티어 배분 대상 종목이 없습니다."]
    cfg = load_tier_weighting_config(tw_cfg)
    guards = cfg["portfolio_guards"]
    warnings: list[str] = []

    core_near = sum(
        v["weight"] for v in holdings.values() if v["tier"] in {"CORE", "NEAR"}
    )
    satellite = sum(v["weight"] for v in holdings.values() if v["tier"] == "SATELLITE")
    hedge_n = sum(1 for v in holdings.values() if v["tier"] == "HEDGE")
    max_w = max((v["weight"] for v in holdings.values()), default=0.0)
    allocatable = [
        v for v in holdings.values()
        if not v.get("excluded_from_allocation") and v.get("tier") != "EXCLUDE"
    ]
    weight_sum = sum(v["weight"] for v in allocatable)

    if abs(weight_sum - 1.0) > 1e-3:
        warnings.append(
            f"배분 합계 {weight_sum:.1%} — 100% 미달 "
            "(single_name_max cap·receiver 부족으로 저투자 — 종목 수·티어 구성 조정 필요)"
        )

    if core_near < float(guards.get("core_near_target_min", 0.65)):
        warnings.append("정책 지연 방어력 부족: CORE+NEAR 합산 비중이 65% 미만입니다.")
    if max_w > float(guards.get("single_name_max", 0.18)) + 1e-6:
        warnings.append(
            f"단일 종목 비중 {max_w:.1%} — {guards.get('single_name_max', 0.18):.0%} 상한 초과 "
            "(cap 재분배 후에도 해소되지 않음 — 종목 수·티어 구성 조정 필요)"
        )
    exclude_n = sum(1 for v in holdings.values() if v.get("tier") == "EXCLUDE")
    if exclude_n:
        warnings.append(f"CECS 미달 EXCLUDE {exclude_n}종 — 배분에서 제외됨(재검토 권장)")
    if hedge_n == 0:
        warnings.append("HEDGE 티어 종목이 0개입니다 — 하방 방어 슬롯 검토 권장")
    if satellite > float(guards.get("satellite_target_max", 0.20)) + 0.05:
        warnings.append(f"SATELLITE 합산 {satellite:.1%} — 목표 상한(20%) 대비 높음")

    return warnings
