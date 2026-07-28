"""Sector coverage metrics — delegates to sector_mapping v0.2."""
from __future__ import annotations

from typing import Any

from src.alpha.sector_mapping import (
    compute_sector_coverage_for_tickers,
    merge_coverage_metrics,
    sector_risk_cap_status,
)

# Backward-compatible alias
compute_candidate_sector_coverage = compute_sector_coverage_for_tickers

__all__ = [
    "compute_candidate_sector_coverage",
    "compute_sector_coverage_for_tickers",
    "merge_coverage_metrics",
    "sector_risk_cap_status",
]
