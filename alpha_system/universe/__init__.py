"""Universe boundary — B안: KOSPI + universe_filter Gate, no financial-only filter."""

from __future__ import annotations

from alpha_system.schema import AlphaSystemConfig, ConfigTodoError, UniverseConfig


def resolve_boundary_mode(cfg: AlphaSystemConfig) -> str:
    mode = cfg.universe.boundary_mode
    if mode is None:
        raise ConfigTodoError(
            "[TODO] universe.boundary_mode unset "
            "(financial | shareholder_return_broad)"
        )
    return mode


def describe_universe_policy(cfg: AlphaSystemConfig) -> dict[str, object]:
    """Human-readable policy snapshot (no live filtering here)."""
    u = cfg.universe
    return {
        "boundary_mode": u.boundary_mode,
        "include_markets": list(u.include_markets),
        "gate_config_path": u.gate_config_path,
        "financial_only_filter": u.financial_only_filter,
        "notes": (
            "KOSPI common stock + data/universe_filter.yaml liquidity/quality Gate. "
            "No financial-industry-only whitelist."
        ),
    }


__all__ = ["UniverseConfig", "resolve_boundary_mode", "describe_universe_policy"]
