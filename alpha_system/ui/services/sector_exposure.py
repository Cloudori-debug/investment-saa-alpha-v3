"""Proposal/ops book sector weight exposure vs sizing.sector_weight_cap (35%)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from alpha_system.sizing.sector_map import concentration_bucket, load_sector_groups

# Sleeve-relative default: matches sizing.sector_weight_cap (locked 0.35).
_DEFAULT_SECTOR_WEIGHT_PCT = 35.0


@dataclass(frozen=True)
class SectorExposure:
    bucket: str
    weight_pct: float
    limit_pct: float
    tickers: tuple[str, ...]
    over: bool
    name_count: int = 0


def load_sector_max(policy_path: Path) -> float:
    """Whole-account policy sector_max (percent). Fallback for legacy callers."""
    if not policy_path.exists():
        return _DEFAULT_SECTOR_WEIGHT_PCT
    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    limits = raw.get("risk_limits") or {}
    return float(limits.get("sector_max", _DEFAULT_SECTOR_WEIGHT_PCT))


def resolve_proposal_sector_limit_pct(data_dir: Path) -> float:
    """Proposal-book sector sum limit: alpha_system sizing.sector_weight_cap × 100."""
    try:
        from alpha_system.loader import load_config

        root = data_dir.parent if data_dir.name == "data" else data_dir
        cfg_path = root / "alpha_system" / "config" / "alpha_system.yaml"
        cfg = load_config(cfg_path if cfg_path.exists() else None)
        return float(cfg.sizing.sector_weight_cap) * 100.0
    except Exception:
        return _DEFAULT_SECTOR_WEIGHT_PCT


def assess_sector_weight_caps(
    rows: Sequence[Any],
    *,
    data_dir: Path,
    sector_max: float | None = None,
) -> list[SectorExposure]:
    """Sum sleeve-relative weights by concentration bucket (financial rollup).

    Over-flag: weight > limit when the bucket has 2+ names (sector cluster),
    or when a single name alone exceeds the same 35% ceiling.
    """
    if not rows:
        return []
    limit = (
        float(sector_max)
        if sector_max is not None
        else resolve_proposal_sector_limit_pct(data_dir)
    )
    mapping = load_sector_groups(str(data_dir.resolve()))
    totals: dict[str, float] = {}
    members: dict[str, list[str]] = {}
    for row in rows:
        ticker = str(getattr(row, "ticker", "")).zfill(6)
        weight = float(getattr(row, "weight_pct", 0.0) or 0.0)
        if weight <= 0:
            continue
        raw_sector = str(getattr(row, "sector", "") or "")
        bucket = concentration_bucket(raw_sector) or mapping.get(ticker, "") or raw_sector
        if not bucket:
            bucket = f"unknown:{ticker}"
        totals[bucket] = totals.get(bucket, 0.0) + weight
        members.setdefault(bucket, []).append(ticker)

    out: list[SectorExposure] = []
    for bucket, w in sorted(totals.items(), key=lambda x: -x[1]):
        names = tuple(members.get(bucket, ()))
        n = len(names)
        # Cap binds for multi-name sectors; single-name uses same ceiling (≡ MV cap).
        over = w > limit + 1e-9 and (n >= 2 or w > limit + 1e-9)
        out.append(
            SectorExposure(
                bucket=bucket,
                weight_pct=round(w, 2),
                limit_pct=limit,
                tickers=names,
                over=over,
                name_count=n,
            )
        )
    return out
