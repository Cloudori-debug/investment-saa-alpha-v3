"""시장·레짐 나침반 P0 v1.0 — 규칙 기반 자산군 목표비중 생성기."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["build_portfolio_allocation", "compute_compass"]

if TYPE_CHECKING:
    from collections.abc import Callable


def __getattr__(name: str) -> Any:
    if name == "build_portfolio_allocation":
        from src.compass.portfolio_builder import build_portfolio_allocation

        return build_portfolio_allocation
    if name == "compute_compass":
        from src.compass.regime_engine import compute_compass

        return compute_compass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
