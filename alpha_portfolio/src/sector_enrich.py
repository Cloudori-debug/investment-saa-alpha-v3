"""Enrich fundamentals/screening rows with KRX sector labels from repo data/."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"

SECTOR_MAPPING_COLUMNS = [
    "ticker",
    "name",
    "market",
    "krx_sector",
    "internal_sector",
    "sector_group",
    "source",
    "asof",
    "is_manual",
    "notes",
]

SOURCE_PRIORITY = {
    "manual": 0,
    "krx_official": 1,
    "name_infer": 2,
    "unknown": 9,
}


def repo_data_dir() -> Path:
    return _DATA_DIR


def _normalize_sector(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "unknown"}:
        return "unknown"
    return text


def _read_mapping_file(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            ticker = str(raw.get("ticker", "")).strip().zfill(6)
            if not ticker:
                continue
            out[ticker] = {k: str(raw.get(k, "") or "") for k in SECTOR_MAPPING_COLUMNS}
    return out


def load_sector_mapping(data_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """Merged mapping: manual > krx_official (mirrors src/alpha/sector_mapping.py)."""
    base = data_dir or _DATA_DIR
    merged: dict[str, dict[str, str]] = {}
    for fname in ("krx_sector_mapping.csv", "krx_sector_mapping_manual.csv"):
        rows = _read_mapping_file(base / fname)
        for tk, row in rows.items():
            existing = merged.get(tk)
            if existing is None:
                merged[tk] = row
                continue
            p_new = SOURCE_PRIORITY.get(row.get("source", ""), 5)
            p_old = SOURCE_PRIORITY.get(existing.get("source", ""), 5)
            if p_new < p_old or (p_new == p_old and row.get("is_manual") == "true"):
                merged[tk] = row
    return merged


def resolve_ticker_sector(
    ticker: str,
    name: str = "",
    universe_sector: str = "",
    *,
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    mapping = mapping or load_sector_mapping()
    tk = str(ticker).zfill(6)
    if tk in mapping:
        row = mapping[tk]
        internal = _normalize_sector(row.get("internal_sector", ""))
        if internal != "unknown":
            group = row.get("sector_group") or internal
            return {
                "sector": row.get("internal_sector") or group,
                "sector_group": group,
                "krx_sector": row.get("krx_sector", ""),
                "source": row.get("source", "krx_official"),
                "resolved": True,
            }
    uni = _normalize_sector(universe_sector)
    if uni != "unknown":
        return {
            "sector": uni,
            "sector_group": uni,
            "krx_sector": uni,
            "source": "universe.csv",
            "resolved": True,
        }
    return {
        "sector": "unknown",
        "sector_group": "unknown",
        "krx_sector": "",
        "source": "unknown",
        "resolved": False,
    }


def enrich_sectors(
    df: pd.DataFrame,
    *,
    data_dir: Path | None = None,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Attach ``sector`` (KRX 업종명) and ``sector_group`` from ``data/krx_sector_mapping*``."""
    if df.empty:
        return df

    mapping = load_sector_mapping(data_dir)
    out = df.copy()
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].astype(str).str.zfill(6)

    if "sector_group" not in out.columns:
        out["sector_group"] = ""
    if "sector_source" not in out.columns:
        out["sector_source"] = ""

    for idx, row in out.iterrows():
        existing = str(row.get("sector", "") or "").strip()
        if existing and existing.lower() != "unknown" and not overwrite:
            continue
        name = str(row.get("name", "") or "")
        resolved = resolve_ticker_sector(
            str(row["ticker"]),
            name,
            existing,
            mapping=mapping,
        )
        sector = str(resolved.get("sector") or "unknown")
        out.at[idx, "sector"] = sector
        out.at[idx, "sector_group"] = str(resolved.get("sector_group") or "")
        out.at[idx, "sector_source"] = str(resolved.get("source") or "")

    return out


def gate_pass_coverage(
    df: pd.DataFrame,
    *,
    data_dir: Path | None = None,
    min_sample: int = 5,
) -> dict[str, Any]:
    """Coverage stats for gate_pass rows (post-enrich or on raw sector column)."""
    if df.empty or "gate_pass" not in df.columns:
        return {"gate_pass": 0, "unknown_count": 0, "unknown_pct": 0.0, "target_met": False}

    work = enrich_sectors(df, data_dir=data_dir) if "sector_source" not in df.columns else df.copy()
    gp = work[work["gate_pass"].astype(str).str.lower() == "true"]
    n = len(gp)
    if n == 0:
        return {"gate_pass": 0, "unknown_count": 0, "unknown_pct": 0.0, "target_met": False}

    sectors = gp["sector"].astype(str).tolist()
    unknown = sum(1 for s in sectors if not s.strip() or s.strip().lower() == "unknown")
    from collections import Counter

    counts = Counter(sectors)
    lt5 = sorted(s for s, c in counts.items() if s and s.lower() != "unknown" and c < min_sample)
    return {
        "gate_pass": n,
        "unknown_count": unknown,
        "unknown_pct": round(100 * unknown / n, 2),
        "target_unknown_pct": 5.0,
        "target_met": (100 * unknown / n) < 5.0,
        "by_sector": dict(counts.most_common()),
        "sectors_sample_lt_5": lt5,
    }
