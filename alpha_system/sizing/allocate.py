"""Tranche sizing — weight_input proportional + iterative initial_weight_cap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from alpha_system.schema import AlphaSystemConfig, TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.sector_map import concentration_bucket


@dataclass(frozen=True)
class NameAllocation:
    ticker: str
    weight_input: float
    incremental_weight: float  # this tranche only
    total_weight_after: float  # existing + incremental
    capped: bool = False


@dataclass
class TrancheAllocationResult:
    tranche_id: TrancheId
    tranche_budget: float
    allocated: list[NameAllocation] = field(default_factory=list)
    unallocated_weight: float = 0.0
    eligible_count: int = 0
    target_names: int = 6
    shortfall_names: int = 0  # max(0, target - eligible)
    warnings: list[str] = field(default_factory=list)

    @property
    def weights(self) -> dict[str, float]:
        return {a.ticker: a.incremental_weight for a in self.allocated if a.incremental_weight > 0}


def locked_sizing(cfg: AlphaSystemConfig) -> tuple[int, float, float]:
    s = cfg.sizing
    return int(s.target_names), float(s.initial_weight_cap), float(s.market_value_cap)


def _sector_bucket(score: NameScore) -> str:
    """Concentration key: known sector_group (with theme rollup), else per-ticker bucket."""
    raw = concentration_bucket(getattr(score, "sector", "") or "")
    if not raw:
        return f"unknown:{score.ticker}"
    return raw


def select_eligible(
    scores: Sequence[NameScore],
    *,
    target_names: int,
    max_names_per_sector: int = 2,
) -> tuple[list[NameScore], list[str]]:
    """
    Eligible = eligibility is True (absolute cutoff passed).
    Never force-fill with eligibility False/None.

    After cutoff, greedily take top weight_input subject to
    max_names_per_sector per normalized sector_group, then stop at
    target_names. Shortfall is allowed — do not relax cutoff or sector cap.
    """
    warnings: list[str] = []
    passed = [s for s in scores if s.eligibility is True]
    if any(s.eligibility is None for s in scores):
        warnings.append(
            "some names have eligibility=None (score_cutoff TODO) — excluded from sizing"
        )
    passed.sort(key=lambda s: s.weight_input, reverse=True)

    selected: list[NameScore] = []
    sector_counts: dict[str, int] = {}
    sector_skips = 0
    for s in passed:
        if len(selected) >= target_names:
            break
        bucket = _sector_bucket(s)
        if sector_counts.get(bucket, 0) >= max_names_per_sector:
            sector_skips += 1
            continue
        selected.append(s)
        sector_counts[bucket] = sector_counts.get(bucket, 0) + 1

    if sector_skips:
        warnings.append(
            f"sector cap: skipped {sector_skips} eligible name(s) "
            f"(max_names_per_sector={max_names_per_sector})"
        )
    if len(passed) > len(selected):
        warnings.append(
            f"eligible={len(passed)} selected={len(selected)} "
            f"(target_names={target_names}, sector_cap={max_names_per_sector})"
        )
    return selected, warnings


def _apply_sector_weight_cap(
    incremental: dict[str, float],
    *,
    existing: Mapping[str, float],
    ticker_sector: Mapping[str, str],
    sector_cap: float,
) -> tuple[dict[str, float], list[str]]:
    """Shrink increments so existing+inc per sector bucket ≤ sector_cap.

    Excess is left unallocated (no cross-sector force-fill). If existing alone
    already exceeds the cap, increments in that sector are zeroed.
    """
    warnings: list[str] = []
    if sector_cap <= 0:
        return incremental, warnings

    buckets: dict[str, list[str]] = {}
    for ticker in incremental:
        bucket = ticker_sector.get(ticker) or f"unknown:{ticker}"
        buckets.setdefault(bucket, []).append(ticker)

    out = dict(incremental)
    for bucket, tickers in buckets.items():
        existing_sum = sum(float(existing.get(t, 0.0)) for t in tickers)
        inc_sum = sum(float(out.get(t, 0.0)) for t in tickers)
        total = existing_sum + inc_sum
        if total <= sector_cap + 1e-12:
            continue
        room = max(0.0, sector_cap - existing_sum)
        if existing_sum > sector_cap + 1e-12:
            for t in tickers:
                out[t] = 0.0
            warnings.append(
                f"sector_weight_cap: bucket={bucket} existing={existing_sum:.4f} "
                f"> cap={sector_cap} — no new allocation in sector"
            )
            continue
        if inc_sum <= 1e-12:
            continue
        scale = room / inc_sum
        for t in tickers:
            out[t] = float(out.get(t, 0.0)) * scale
        warnings.append(
            f"sector_weight_cap: bucket={bucket} scaled to ≤{sector_cap} "
            f"(was {total:.4f}, names={len(tickers)})"
        )
    return out, warnings


def allocate_tranche(
    cfg: AlphaSystemConfig,
    *,
    tranche_id: TrancheId,
    scores: Sequence[NameScore],
    existing_weights: Mapping[str, float] | None = None,
    tranche_budget: float | None = None,
) -> TrancheAllocationResult:
    """
    Allocate one tranche budget across eligible names.

    Cap rule: (existing_weight + incremental) <= initial_weight_cap.
    Sector rule: sum of weights in a concentration bucket ≤ sector_weight_cap
    when 2+ names (also binds single-name via market_value_cap alignment at 35%).
    Iterative capping redistributes surplus to uncapped peers.
    If no receivers remain, leftover stays unallocated + WARN
    (do not force-fill below absolute cutoff).
    """
    target_names, initial_cap, _mv_cap = locked_sizing(cfg)
    max_per_sector = int(getattr(cfg.sizing, "max_names_per_sector", 2) or 2)
    sector_cap = float(getattr(cfg.sizing, "sector_weight_cap", 0.35) or 0.35)
    budget = (
        float(tranche_budget)
        if tranche_budget is not None
        else float(cfg.tranches[tranche_id.value].weight)
    )
    existing = {k: float(v) for k, v in (existing_weights or {}).items()}

    eligible, warnings = select_eligible(
        scores,
        target_names=target_names,
        max_names_per_sector=max_per_sector,
    )
    shortfall = max(0, target_names - len(eligible))
    if shortfall:
        warnings.append(
            f"eligible names shortfall: have={len(eligible)} target={target_names} "
            f"(shortfall={shortfall}) — do not force-fill ineligible"
        )

    result = TrancheAllocationResult(
        tranche_id=tranche_id,
        tranche_budget=budget,
        eligible_count=len(eligible),
        target_names=target_names,
        shortfall_names=shortfall,
        warnings=list(warnings),
    )

    if not eligible or budget <= 0:
        result.unallocated_weight = budget
        if budget > 0 and not eligible:
            result.warnings.append(
                "no eligible names — entire tranche budget left unallocated"
            )
        return result

    # Room under cap given existing holdings
    room = {
        s.ticker: max(0.0, initial_cap - existing.get(s.ticker, 0.0))
        for s in eligible
    }
    # Proportional raw by weight_input among those with room > 0
    active = [s for s in eligible if room[s.ticker] > 1e-12]
    if not active:
        result.unallocated_weight = budget
        result.warnings.append(
            "WARN: all eligible names already at initial_weight_cap "
            f"({initial_cap}) with existing holdings — tranche left unallocated"
        )
        result.allocated = [
            NameAllocation(
                ticker=s.ticker,
                weight_input=s.weight_input,
                incremental_weight=0.0,
                total_weight_after=existing.get(s.ticker, 0.0),
                capped=True,
            )
            for s in eligible
        ]
        return result

    wi_sum = sum(max(s.weight_input, 0.0) for s in active) or 1.0
    incremental = {
        s.ticker: budget * (max(s.weight_input, 0.0) / wi_sum) for s in active
    }

    # Iterative cap vs (existing + incremental); redistribute by remaining room
    for _ in range(64):
        surplus = 0.0
        for t, w in list(incremental.items()):
            allowed = max(0.0, initial_cap - existing.get(t, 0.0))
            if w > allowed + 1e-12:
                surplus += w - allowed
                incremental[t] = allowed
        if surplus <= 1e-12:
            break
        rooms = {
            t: max(0.0, initial_cap - existing.get(t, 0.0) - incremental[t])
            for t in incremental
        }
        room_sum = sum(rooms.values())
        if room_sum <= 1e-12:
            break
        for t in incremental:
            incremental[t] += surplus * (rooms[t] / room_sum)

    ticker_sector = {s.ticker: _sector_bucket(s) for s in eligible}
    # Cap binds when a concentration bucket has 2+ names among this tranche's eligible.
    sector_counts: dict[str, int] = {}
    for bucket in ticker_sector.values():
        sector_counts[bucket] = sector_counts.get(bucket, 0) + 1
    multi_inc = {
        t: w
        for t, w in incremental.items()
        if sector_counts.get(ticker_sector.get(t, ""), 0) >= 2
    }
    if multi_inc:
        capped_inc, sector_warns = _apply_sector_weight_cap(
            multi_inc,
            existing=existing,
            ticker_sector=ticker_sector,
            sector_cap=sector_cap,
        )
        incremental.update(capped_inc)
        result.warnings.extend(sector_warns)

    allocated_sum = sum(incremental.values())
    unallocated = max(0.0, budget - allocated_sum)
    if unallocated > 1e-9:
        result.warnings.append(
            f"WARN: unallocated_weight={unallocated:.6f} after iterative capping "
            f"(initial_weight_cap={initial_cap}, sector_weight_cap={sector_cap}); "
            "leave unexecuted in tranche — do not force-fill"
        )

    result.unallocated_weight = round(unallocated, 8)
    result.allocated = []
    for s in eligible:
        inc = float(incremental.get(s.ticker, 0.0))
        total = existing.get(s.ticker, 0.0) + inc
        result.allocated.append(
            NameAllocation(
                ticker=s.ticker,
                weight_input=s.weight_input,
                incremental_weight=round(inc, 8),
                total_weight_after=round(total, 8),
                capped=total >= initial_cap - 1e-9,
            )
        )
    return result


def require_sizing(cfg: AlphaSystemConfig) -> tuple[int, float, float]:
    """Return locked (target_names, initial_weight_cap, market_value_cap)."""
    return locked_sizing(cfg)
