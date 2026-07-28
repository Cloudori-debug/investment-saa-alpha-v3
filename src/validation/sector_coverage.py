"""Candidate sector coverage metrics — read-only diagnostics, no scoring changes."""
from __future__ import annotations

from typing import Any

from src.field_normalize import normalize_sector


def compute_candidate_sector_coverage(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Sector fill rate for a candidate list (shortlist, top-N, etc.)."""
    if not candidates:
        return {
            "count": 0,
            "unknown_count": 0,
            "unknown_rate": 0.0,
            "candidate_sector_coverage_pct": 0.0,
            "shortlist_unknown_rate": 0.0,
            "filled_sectors": {},
        }
    sectors = [normalize_sector(c.get("sector", "")) for c in candidates]
    unknown = sum(1 for s in sectors if s == "unknown")
    n = len(sectors)
    filled: dict[str, int] = {}
    for s in sectors:
        if s != "unknown":
            filled[s] = filled.get(s, 0) + 1
    coverage_pct = round(100 * (n - unknown) / n, 1)
    unknown_rate = round(unknown / n, 4)
    return {
        "count": n,
        "unknown_count": unknown,
        "unknown_rate": unknown_rate,
        "candidate_sector_coverage_pct": coverage_pct,
        "shortlist_unknown_rate": unknown_rate,
        "filled_sectors": filled,
    }


def merge_coverage_metrics(
    shortlist: dict[str, Any],
    top10: dict[str, Any],
    holdings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combined sector coverage block for reports and gates."""
    if holdings is not None:
        from src.alpha.sector_mapping import merge_coverage_metrics as _merge

        return _merge(shortlist, top10, holdings)
    return {
        "candidate_sector_coverage_pct": shortlist.get("candidate_sector_coverage_pct", 0.0),
        "shortlist_unknown_rate": shortlist.get("unknown_rate", 0.0),
        "shortlist_unknown_count": shortlist.get("unknown_count", 0),
        "shortlist_count": shortlist.get("count", 0),
        "top10_unknown_rate": top10.get("unknown_rate", 0.0),
        "top10_unknown_count": top10.get("unknown_count", 0),
        "top10_count": top10.get("count", 0),
        "top10_sector_coverage_pct": top10.get("candidate_sector_coverage_pct", 0.0),
    }
