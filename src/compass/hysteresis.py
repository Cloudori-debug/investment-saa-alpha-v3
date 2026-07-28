"""Bry-Boschan-style minimum-duration hysteresis for compass regime/phase.

CRISIS asymmetry (safety): enter CRISIS immediately; exit CRISIS only after
confirm_runs consecutive non-CRISIS computations. Documented in ECONOMIC_COMPASS RESULT.
"""
from __future__ import annotations

from typing import Any

from src.compass.models import MarketPhase, RiskRegime


def _parse_regime(value: Any) -> RiskRegime | None:
    if value is None:
        return None
    try:
        return RiskRegime(str(value))
    except ValueError:
        return None


def _parse_phase(value: Any) -> MarketPhase | None:
    if value is None:
        return None
    try:
        return MarketPhase(str(value))
    except ValueError:
        return None


def _confirm_runs(rules: dict[str, Any], key: str, default: int = 2) -> int:
    raw = (rules.get("hysteresis") or {}).get(key, default)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, n)


def _last_applied_regime(history: list[dict[str, Any]]) -> RiskRegime | None:
    for row in reversed(history):
        parsed = _parse_regime(row.get("applied_regime"))
        if parsed is not None:
            return parsed
    return None


def _last_applied_phase(history: list[dict[str, Any]]) -> MarketPhase | None:
    for row in reversed(history):
        parsed = _parse_phase(row.get("market_phase")) or _parse_phase(row.get("computed_market_phase"))
        if parsed is not None:
            return parsed
    return None


def _consecutive_computed_match(
    history: list[dict[str, Any]],
    *,
    field: str,
    target: str,
    need: int,
) -> bool:
    """True if last `need` values of field (+ today's target) all equal target."""
    if need <= 1:
        return True
    series = [str(row.get(field) or "") for row in history]
    series.append(target)
    if len(series) < need:
        return False
    return all(v == target for v in series[-need:])


def apply_regime_hysteresis(
    computed: RiskRegime,
    history: list[dict[str, Any]],
    rules: dict[str, Any],
) -> tuple[RiskRegime, str | None]:
    """Return (applied_regime, note). CRISIS entry is immediate; exit needs confirm_runs."""
    confirm = _confirm_runs(rules, "regime_confirm_runs", 2)
    previous = _last_applied_regime(history)

    if previous is None:
        return computed, "hysteresis_bootstrap"

    if computed == RiskRegime.CRISIS:
        if previous != RiskRegime.CRISIS:
            return RiskRegime.CRISIS, "crisis_entry_immediate"
        return RiskRegime.CRISIS, None

    if previous == RiskRegime.CRISIS:
        if _consecutive_computed_match(
            history, field="computed_regime", target=computed.value, need=confirm,
        ):
            return computed, "crisis_exit_confirmed"
        return RiskRegime.CRISIS, "crisis_exit_pending"

    if computed == previous:
        return previous, None

    if _consecutive_computed_match(
        history, field="computed_regime", target=computed.value, need=confirm,
    ):
        return computed, "regime_confirmed"
    return previous, "regime_hold_pending"


def apply_phase_hysteresis(
    computed: MarketPhase,
    history: list[dict[str, Any]],
    rules: dict[str, Any],
) -> tuple[MarketPhase, str | None]:
    confirm = _confirm_runs(rules, "phase_confirm_runs", 2)
    previous = _last_applied_phase(history)

    if previous is None:
        return computed, "phase_hysteresis_bootstrap"

    if computed == previous:
        return previous, None

    field = "computed_market_phase"
    if not any(row.get("computed_market_phase") for row in history):
        field = "market_phase"

    if _consecutive_computed_match(
        history, field=field, target=computed.value, need=confirm,
    ):
        return computed, "phase_confirmed"
    return previous, "phase_hold_pending"
