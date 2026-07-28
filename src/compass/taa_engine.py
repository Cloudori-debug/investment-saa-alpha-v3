from __future__ import annotations

from typing import Any

from src.compass.models import MarketPhase, RiskRegime


PHASE_TILT_KEYS: dict[MarketPhase, list[str]] = {
    MarketPhase.MARKET_RECOVERY: ["MARKET_RECOVERY", "RECOVERY"],
    MarketPhase.MARKET_EXPANSION: ["MARKET_EXPANSION", "EXPANSION"],
    MarketPhase.MARKET_SLOWDOWN: ["MARKET_SLOWDOWN", "SLOWDOWN"],
    MarketPhase.MARKET_CONTRACTION: ["MARKET_CONTRACTION", "CONTRACTION"],
}


def get_regime_tilts(profiles: dict[str, Any], regime: RiskRegime) -> dict[str, float]:
    tilts = profiles.get("taa_tilts", {}).get(regime.value, {})
    return {str(k): float(v) for k, v in tilts.items()}


def get_phase_tilts(profiles: dict[str, Any], phase: MarketPhase) -> dict[str, float]:
    if phase == MarketPhase.UNKNOWN:
        return {}
    phase_tilts = profiles.get("phase_tilts", {})
    for key in PHASE_TILT_KEYS.get(phase, [phase.value]):
        if key in phase_tilts:
            return {str(k): float(v) for k, v in phase_tilts[key].items()}
    return {}


def merge_tilts(*tilt_maps: dict[str, float]) -> dict[str, float]:
    merged: dict[str, float] = {}
    for tilt_map in tilt_maps:
        for group, value in tilt_map.items():
            merged[group] = merged.get(group, 0.0) + value
    return merged
