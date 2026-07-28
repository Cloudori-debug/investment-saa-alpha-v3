from __future__ import annotations

from src.models import DataGate, MarketIndicators


def classify_data_gate_from_regime(regime: str, base_gate: DataGate) -> DataGate:
    upper = regime.upper()
    if "CRISIS" in upper or "RED" in upper:
        return "RED" if base_gate == "RED" else "YELLOW"
    return base_gate


def parse_regime(market: MarketIndicators) -> dict[str, str]:
    raw = market.regime.upper()
    return {
        "raw": market.regime,
        "normalized": raw,
        "is_stable": "STABLE" in raw or "NEUTRAL" in raw or "GREEN" in raw,
        "is_risk_off": "RISK_OFF" in raw or "RED" in raw,
        "is_caution": "YELLOW" in raw or "CAUTION" in raw,
    }


def execution_level_hint(
    data_gate: DataGate,
    regime_info: dict[str, str],
    max_abs_gap: float,
) -> int:
    if data_gate == "RED":
        return 0
    if regime_info.get("is_risk_off"):
        return 4
    if max_abs_gap >= 5:
        return 3
    if max_abs_gap >= 1:
        return 2
    return 1
