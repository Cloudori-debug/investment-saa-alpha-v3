"""Flow row cache — PyKRX miss fail-soft with stale fallback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.alpha_flow.flow_classifier import STALE_STALENESS_DAYS_THRESHOLD, is_flow_record_stale


def cache_dir(data_dir: Path) -> Path:
    return data_dir / "cache" / "flow_refresh"


def load_cached_flow_row(data_dir: Path, ticker: str, as_of: str) -> dict[str, Any] | None:
    """Read per-ticker cache file if present within stale threshold."""
    from src.alpha.flow_refresh import _read_cache

    tk = str(ticker).zfill(6)
    row, _status = _read_cache(data_dir, tk, as_of[:10], max_age_days=STALE_STALENESS_DAYS_THRESHOLD)
    if row is None:
        return None
    return dict(row)


def save_cached_flow_row(data_dir: Path, ticker: str, as_of: str, row: dict[str, Any]) -> None:
    from src.alpha.flow_refresh import _write_cache

    _write_cache(data_dir, str(ticker).zfill(6), as_of[:10], row)


def load_cache_fallback_row(
    data_dir: Path,
    ticker: str,
    as_of: str,
    *,
    existing: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """PyKRX failure: use cache or prior investor_flows row; mark stale with warnings."""
    warnings: list[str] = []
    tk = str(ticker).zfill(6)
    cached = load_cached_flow_row(data_dir, tk, as_of)
    if cached and not is_flow_record_stale(cached):
        warnings.append(f"PyKRX miss — using cache for {tk}")
        return cached, warnings

    if existing and str(existing.get("source") or "") not in {"template", "missing", ""}:
        row = dict(existing)
        row["flow_signal"] = "STALE"
        row["flow_score"] = 0.0
        row["staleness_days"] = max(int(row.get("staleness_days") or 0), STALE_STALENESS_DAYS_THRESHOLD)
        row["stale_flag"] = True
        warnings.append(f"PyKRX miss — stale fallback from prior row for {tk}")
        return row, warnings

    warnings.append(f"PyKRX miss — no cache for {tk}")
    return {
        "date": as_of[:10],
        "ticker": tk,
        "flow_signal": "STALE",
        "flow_score": 0.0,
        "source": "missing",
        "staleness_days": 999,
        "stale_flag": True,
    }, warnings


def read_flow_cache_meta(data_dir: Path) -> dict[str, Any]:
    """Summary of on-disk flow cache directory."""
    root = cache_dir(data_dir)
    if not root.exists():
        return {"cache_files": 0, "cache_dir": str(root)}
    files = list(root.glob("*.json"))
    return {
        "cache_files": len(files),
        "cache_dir": str(root),
    }


def write_flow_cache_index(data_dir: Path, meta: dict[str, Any]) -> Path:
    path = cache_dir(data_dir) / "_flow_cache_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
