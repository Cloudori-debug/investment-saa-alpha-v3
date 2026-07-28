from __future__ import annotations

from typing import Any

from src.alpha_v2.schemas import (
    FINAL_MAX,
    FINAL_MIN,
    KOSDAQ_FINAL_MAX,
    KOSDAQ_FINAL_MIN,
    KOSDAQ_SINGLE_WEIGHT_MAX,
    KOSDAQ_SLEEVE_MAX_PCT,
    KOSPI_FINAL_MAX,
    KOSPI_FINAL_MIN,
    KOSPI_SINGLE_WEIGHT_MAX,
    SECTOR_CAP_PCT,
    TOP30_MAX,
)


def _suggested_weight(market: str, rank: int) -> float:
    if market.upper() == "KOSDAQ":
        return min(KOSDAQ_SINGLE_WEIGHT_MAX, max(2.0, 5.0 - rank * 0.3))
    return min(KOSPI_SINGLE_WEIGHT_MAX, max(3.0, 7.0 - rank * 0.25))


def select_top30(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [r for r in scored if r.get("tier") != "Exclude" and r.get("grade") != "Reject"]
    ranked = sorted(eligible, key=lambda r: (-float(r.get("total_score_v2_shadow", 0)), r["ticker"]))
    top = ranked[:TOP30_MAX]
    for i, row in enumerate(top, start=1):
        row["rank"] = i
    return top


def select_final_candidates(top30: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick 5~8 names with KOSPI/KOSDAQ and sector constraints."""
    pool = sorted(top30, key=lambda r: (-float(r.get("total_score_v2_shadow", 0)), r["ticker"]))
    selected: list[dict[str, Any]] = []
    selected_tickers: set[str] = set()
    kosdaq_count = 0
    kospi_count = 0
    sector_weights: dict[str, float] = {}
    kosdaq_weight = 0.0

    for row in pool:
        if len(selected) >= FINAL_MAX:
            break
        ticker = row["ticker"]
        if ticker in selected_tickers:
            continue
        market = str(row.get("market", "KOSPI")).upper()
        sector = str(row.get("sector") or "unknown")
        weight = _suggested_weight(market, len(selected) + 1)

        if market == "KOSDAQ":
            if kosdaq_count >= KOSDAQ_FINAL_MAX:
                continue
            if row.get("shadow_watch"):
                weight = min(weight, KOSDAQ_SINGLE_WEIGHT_MAX)
            if kosdaq_weight + weight > KOSDAQ_SLEEVE_MAX_PCT and kosdaq_count >= KOSDAQ_FINAL_MIN:
                continue
        else:
            if kospi_count >= KOSPI_FINAL_MAX:
                continue

        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        if sector_weights[sector] > SECTOR_CAP_PCT:
            sector_weights[sector] -= weight
            continue

        cand = dict(row)
        cand["suggested_shadow_weight"] = round(weight, 2)
        cand["final_rank"] = len(selected) + 1
        selected.append(cand)
        selected_tickers.add(ticker)

        if market == "KOSDAQ":
            kosdaq_count += 1
            kosdaq_weight += weight
        else:
            kospi_count += 1

    if len(selected) < FINAL_MIN:
        for row in pool:
            if row["ticker"] in selected_tickers:
                continue
            market = str(row.get("market", "KOSPI")).upper()
            if market == "KOSDAQ" and kosdaq_count >= KOSDAQ_FINAL_MAX:
                continue
            if len(selected) >= FINAL_MIN:
                break
            cand = dict(row)
            cand["suggested_shadow_weight"] = round(_suggested_weight(str(row.get("market", "KOSPI")), len(selected) + 1), 2)
            cand["final_rank"] = len(selected) + 1
            selected.append(cand)
            selected_tickers.add(row["ticker"])
            if market == "KOSDAQ":
                kosdaq_count += 1

    return selected[:FINAL_MAX]
