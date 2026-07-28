from __future__ import annotations

from typing import Any

from src.compass.models import CompassResult, GroupAllocation, PortfolioAllocation
from src.compass.profile_aliases import resolve_profile_name
from src.compass.saa_engine import get_group_bounds, get_saa_weights
from src.compass.taa_engine import get_phase_tilts, get_regime_tilts
from src.exposure.ar11_target_integrity import get_locked_tilt_groups, zero_tilts_for_locked_groups
from src.models import VALID_ASSET_GROUPS


def resolve_taa_tilt_scale(rules: dict[str, Any] | None) -> float:
    """Return TAA tilt scale from compass_rules; missing key → 1.0 (legacy)."""
    if not rules:
        return 1.0
    try:
        return float((rules.get("tilt_governance") or {}).get("taa_tilt_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _clamp_weights(weights: dict[str, float], bounds: dict[str, dict[str, float]]) -> dict[str, float]:
    clamped: dict[str, float] = {}
    for group, w in weights.items():
        b = bounds.get(group, {"min": 0, "max": 100})
        clamped[group] = max(b["min"], min(b["max"], w))
    return clamped


def _normalize_to_100(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("allocation weights sum to zero")
    return {k: round(v / total * 100, 2) for k, v in weights.items()}


def _within_bounds(weights: dict[str, float], bounds: dict[str, dict[str, float]], tol: float = 0.01) -> bool:
    for group, w in weights.items():
        b = bounds.get(group, {"min": 0, "max": 100})
        if w < b["min"] - tol or w > b["max"] + tol:
            return False
    return True


def apply_bounds_iterative(
    weights: dict[str, float],
    bounds: dict[str, dict[str, float]],
    *,
    max_iter: int = 20,
    tol: float = 0.01,
) -> tuple[dict[str, float], list[str]]:
    """Clamp → normalize 반복으로 min/max 재위반을 최소화."""
    notes: list[str] = []
    current = dict(weights)

    for iteration in range(max_iter):
        before = dict(current)
        current = _clamp_weights(current, bounds)
        for group, w in current.items():
            b = bounds.get(group, {"min": 0, "max": 100})
            if before[group] < b["min"] - tol:
                notes.append(f"{group}: {before[group]:.1f}% → 하한 {b['min']}% 적용")
            elif before[group] > b["max"] + tol:
                notes.append(f"{group}: {before[group]:.1f}% → 상한 {b['max']}% 적용")
        current = _normalize_to_100(current)
        if _within_bounds(current, bounds, tol):
            break

    if not _within_bounds(current, bounds, tol):
        current = _clamp_weights(current, bounds)
        current = _normalize_to_100(current)
        notes.append("bounds: 반복 보정 후에도 일부 제약 근접 — 최종 clamp 적용")

    return current, notes


def build_portfolio_allocation(
    compass: CompassResult,
    profiles: dict[str, Any],
    profile_name: str | None = None,
    *,
    rules: dict[str, Any] | None = None,
    tilt_meta: dict[str, Any] | None = None,
) -> PortfolioAllocation:
    name = resolve_profile_name(profiles, profile_name)
    saa = get_saa_weights(profiles, name)
    bounds = get_group_bounds(profiles, name)
    regime_tilts_raw = get_regime_tilts(profiles, compass.applied_regime)
    phase_tilts_raw = get_phase_tilts(profiles, compass.market_phase)
    locked = get_locked_tilt_groups(profiles, name)
    regime_tilts_raw = zero_tilts_for_locked_groups(regime_tilts_raw, locked)
    phase_tilts_raw = zero_tilts_for_locked_groups(phase_tilts_raw, locked)

    tilt_scale = resolve_taa_tilt_scale(rules)
    all_groups = sorted(VALID_ASSET_GROUPS)
    scaled_phase = {g: float(phase_tilts_raw.get(g, 0.0)) * tilt_scale for g in all_groups}
    scaled_regime = {g: float(regime_tilts_raw.get(g, 0.0)) * tilt_scale for g in all_groups}

    raw_effective: dict[str, float] = {}
    for group in all_groups:
        base = saa.get(group, 0.0)
        raw_effective[group] = base + scaled_phase[group] + scaled_regime[group]

    final, bound_notes = apply_bounds_iterative(raw_effective, bounds)

    group_rows: list[GroupAllocation] = []
    for group in all_groups:
        base = saa.get(group, 0.0)
        p_tilt = scaled_phase[group]
        r_tilt = scaled_regime[group]
        b = bounds.get(group, {"min": 0, "max": 100})
        group_rows.append(
            GroupAllocation(
                asset_group=group,
                saa_weight=base,
                phase_tilt=round(p_tilt, 2),
                regime_tilt=round(r_tilt, 2),
                raw_target=round(base + p_tilt + r_tilt, 2),
                final_target=final.get(group, 0.0),
                min_weight=b["min"],
                max_weight=b["max"],
            )
        )

    notes = [
        f"SAA 프로필: {name}",
        f"적용 레짐 TAA: {compass.applied_regime.value}",
        f"시장 국면 보정: {compass.market_phase.value}",
        f"TAA tilt scale: {tilt_scale}",
    ]
    if compass.override.active:
        notes.append(
            f"수동 레짐 override: {compass.manual_regime} → {compass.applied_regime.value}"
            + (f" ({compass.override.reason})" if compass.override.reason else "")
        )
    notes.extend(bound_notes)

    if tilt_meta is not None:
        tilt_meta.clear()
        tilt_meta.update(
            {
                "taa_tilt_scale": tilt_scale,
                "raw_phase_tilt": {g: round(float(phase_tilts_raw.get(g, 0.0)), 4) for g in all_groups},
                "raw_regime_tilt": {g: round(float(regime_tilts_raw.get(g, 0.0)), 4) for g in all_groups},
                "scaled_phase_tilt": {g: round(scaled_phase[g], 4) for g in all_groups},
                "scaled_regime_tilt": {g: round(scaled_regime[g], 4) for g in all_groups},
            }
        )

    return PortfolioAllocation(
        profile=name,
        market_phase=compass.market_phase,
        applied_regime=compass.applied_regime,
        compass_direction=compass.compass_direction,
        groups=group_rows,
        total_weight=round(sum(g.final_target for g in group_rows), 2),
        notes=notes,
    )
