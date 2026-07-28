"""Normalized sector_group lookup for concentration caps (KRX mapping SoT)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Mapping

_SOURCE_PRIORITY = {
    "manual": 0,
    "krx_official": 1,
    "name_infer": 2,
    "unknown": 9,
}

# Concentration rollups: fine KRX groups that share the same theme risk.
# Peer scoring still uses raw labels; select_eligible + sector weight caps use this.
CONCENTRATION_ALIASES: Mapping[str, str] = {
    "financial_bank": "financial",  # 은행 ≡ 금융지주
    "insurance": "financial",  # 손보·생보 ≡ 금융 매크로(금리·신용) 테마
    "financial_brokerage": "financial",  # 증권 ≡ 금융 테마
}


def _normalize(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "unknown", "none"}:
        return ""
    return text


def concentration_bucket(sector_group: object) -> str:
    """Theme key for max_names_per_sector (after alias rollup)."""
    raw = _normalize(sector_group)
    if not raw:
        return ""
    return str(CONCENTRATION_ALIASES.get(raw, raw))


def _read_mapping(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            ticker = str(raw.get("ticker", "")).strip().zfill(6)
            if not ticker:
                continue
            out[ticker] = {
                "sector_group": str(raw.get("sector_group", "") or ""),
                "internal_sector": str(raw.get("internal_sector", "") or ""),
                "source": str(raw.get("source", "") or ""),
                "is_manual": str(raw.get("is_manual", "") or ""),
            }
    return out


@lru_cache(maxsize=4)
def load_sector_groups(data_dir: str) -> Mapping[str, str]:
    """Return ticker → concentration sector_group from data/krx_sector_mapping*.csv."""
    base = Path(data_dir)
    merged: dict[str, dict[str, str]] = {}
    for fname in ("krx_sector_mapping.csv", "krx_sector_mapping_manual.csv"):
        for ticker, row in _read_mapping(base / fname).items():
            existing = merged.get(ticker)
            if existing is None:
                merged[ticker] = row
                continue
            p_new = _SOURCE_PRIORITY.get(row.get("source", ""), 5)
            p_old = _SOURCE_PRIORITY.get(existing.get("source", ""), 5)
            if p_new < p_old or (p_new == p_old and row.get("is_manual") == "true"):
                merged[ticker] = row

    out: dict[str, str] = {}
    for ticker, row in merged.items():
        group = _normalize(row.get("sector_group")) or _normalize(row.get("internal_sector"))
        group = concentration_bucket(group)
        if group:
            out[ticker] = group
    return out


def resolve_sector_group(
    ticker: str,
    *,
    data_dir: Path | None = None,
    mapping: Mapping[str, str] | None = None,
) -> str:
    """Concentration key for a ticker. Empty string if unresolved."""
    tk = str(ticker).zfill(6)
    if mapping is not None:
        return concentration_bucket(mapping.get(tk, ""))
    if data_dir is None:
        return ""
    return str(load_sector_groups(str(data_dir.resolve())).get(tk, "") or "")
