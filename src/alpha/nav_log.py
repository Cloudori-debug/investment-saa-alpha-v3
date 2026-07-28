from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.data_loader import load_positions
from src.exposure.core_saa_reference import load_core_saa_reference

NAV_LOG_FIELDS = [
    "date",
    "run_id",
    "total_nav_krw",
    "cash_krw",
    "positions_value_krw",
    "kr_alpha_value_krw",
    "core_reference_held_krw",
    "satellite_other_krw",
]

# Heuristic: NAV jump dominated by cash/core buckets ≈ capital add / asset registration
# (no dedicated cashflow event log exists in this system).
_JUMP_PCT_THRESHOLD = 0.05
_BUCKET_DOMINANCE_SHARE = 0.70


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip().upper()
    return t if t == "CASH" else t.zfill(6) if t.isdigit() else t


def build_nav_snapshot(
    data_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> dict[str, Any]:
    positions = load_positions(data_dir / "positions.csv")
    core_tickers: set[str] = set()
    ref = load_core_saa_reference(data_dir)
    if ref:
        for asset in ref.get("assets") or []:
            t = asset.get("ticker")
            if t:
                core_tickers.add(_normalize_ticker(str(t)))

    total = 0.0
    cash = 0.0
    kr_alpha = 0.0
    core_held = 0.0
    other = 0.0

    for p in positions:
        val = float(p.current_value or 0)
        total += val
        t = _normalize_ticker(p.ticker)
        if t == "CASH":
            cash += val
            continue
        if p.asset_group == "kr_alpha":
            kr_alpha += val
        elif t in core_tickers:
            core_held += val
        else:
            other += val

    return {
        "date": as_of[:10],
        "run_id": run_id,
        "total_nav_krw": int(round(total)),
        "cash_krw": int(round(cash)),
        "positions_value_krw": int(round(total - cash)),
        "kr_alpha_value_krw": int(round(kr_alpha)),
        "core_reference_held_krw": int(round(core_held)),
        "satellite_other_krw": int(round(other)),
    }


def append_portfolio_nav_log(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=NAV_LOG_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: snapshot.get(k, "") for k in NAV_LOG_FIELDS})


def _f(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _month_eod_rows(log_path: Path, as_of: str) -> list[dict[str, str]]:
    """Keep last snapshot per calendar date within as_of month (and <= as_of)."""
    if not log_path.exists():
        return []
    by_date: dict[str, dict[str, str]] = {}
    month = as_of[:7]
    with log_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            d = str(row.get("date") or "")[:10]
            if not d or d[:7] != month or d > as_of[:10]:
                continue
            by_date[d] = row
    return [by_date[k] for k in sorted(by_date)]


def detect_nav_capital_like_events(month_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Infer capital-add / registration jumps from bucket deltas (no cashflow ledger)."""
    events: list[dict[str, Any]] = []
    for prev, cur in zip(month_rows, month_rows[1:]):
        t0 = _f(prev, "total_nav_krw")
        t1 = _f(cur, "total_nav_krw")
        if t0 <= 0:
            continue
        d_total = t1 - t0
        pct = abs(d_total) / t0
        if pct < _JUMP_PCT_THRESHOLD:
            continue
        d_core = _f(cur, "core_reference_held_krw") - _f(prev, "core_reference_held_krw")
        d_cash = _f(cur, "cash_krw") - _f(prev, "cash_krw")
        d_alpha = _f(cur, "kr_alpha_value_krw") - _f(prev, "kr_alpha_value_krw")
        d_other = _f(cur, "satellite_other_krw") - _f(prev, "satellite_other_krw")
        denom = max(abs(d_total), 1.0)
        core_share = abs(d_core) / denom
        cash_share = abs(d_cash) / denom
        if core_share < _BUCKET_DOMINANCE_SHARE and cash_share < _BUCKET_DOMINANCE_SHARE:
            continue
        estimated_flow = d_core + d_cash
        # Prefer signed total when buckets nearly explain the jump.
        if abs(estimated_flow - d_total) / denom <= 0.15:
            estimated_flow = d_total
        events.append({
            "from_date": str(prev.get("date") or "")[:10],
            "to_date": str(cur.get("date") or "")[:10],
            "delta_total_nav_krw": int(round(d_total)),
            "delta_core_reference_held_krw": int(round(d_core)),
            "delta_cash_krw": int(round(d_cash)),
            "delta_kr_alpha_krw": int(round(d_alpha)),
            "delta_satellite_other_krw": int(round(d_other)),
            "estimated_external_flow_krw": int(round(estimated_flow)),
            "reason": "nav_jump_dominated_by_cash_or_core_reference",
            "method": "heuristic_bucket_delta",
            "note": (
                "No cashflow event log exists; treated as capital/registration, "
                "not trading P&L."
            ),
        })
    return events


def nav_return_mtd_detail(log_path: Path, as_of: str) -> dict[str, Any]:
    """MTD NAV returns with optional capital/registration adjustment.

    Important: this system has no deposit/capital-event ledger. Adjustment uses
    heuristic jumps where cash/core_reference buckets dominate large NAV changes.
    """
    month_rows = _month_eod_rows(log_path, as_of)
    empty = {
        "raw_nav_return_mtd": None,
        "adjusted_nav_return_mtd": None,
        "estimated_external_flow_mtd_krw": 0,
        "capital_like_events": [],
        "quality": "missing_nav_log",
        "method": "eod_snapshot_ratio",
    }
    if not month_rows:
        return empty

    first = _f(month_rows[0], "total_nav_krw")
    latest = _f(month_rows[-1], "total_nav_krw")
    if first <= 0 or latest <= 0:
        empty["quality"] = "invalid_nav"
        return empty

    raw = round((latest / first - 1) * 100, 4)
    events = detect_nav_capital_like_events(month_rows)
    flow_sum = sum(int(e.get("estimated_external_flow_krw") or 0) for e in events)
    adjusted_nav = latest - flow_sum
    adjusted = None
    if adjusted_nav > 0:
        adjusted = round((adjusted_nav / first - 1) * 100, 4)

    quality = "ok"
    if events:
        quality = "adjusted_for_capital_like_jumps"
    elif abs(raw) >= 20:
        quality = "large_raw_move_no_capital_event_detected"

    return {
        "raw_nav_return_mtd": raw,
        "adjusted_nav_return_mtd": adjusted,
        "estimated_external_flow_mtd_krw": int(flow_sum),
        "capital_like_events": events,
        "month_start_nav_krw": int(round(first)),
        "latest_nav_krw": int(round(latest)),
        "adjusted_latest_nav_krw": int(round(adjusted_nav)) if adjusted_nav > 0 else None,
        "quality": quality,
        "method": "eod_snapshot_ratio_minus_heuristic_external_flow",
        "limitation": (
            "No authoritative cashflow/registration ledger; "
            "adjustment is heuristic from NAV bucket deltas."
        ),
    }


def nav_return_mtd(log_path: Path, as_of: str) -> float | None:
    """Backward compatible: prefer adjusted MTD when capital-like jumps exist."""
    detail = nav_return_mtd_detail(log_path, as_of)
    if detail.get("adjusted_nav_return_mtd") is not None:
        return float(detail["adjusted_nav_return_mtd"])
    raw = detail.get("raw_nav_return_mtd")
    return float(raw) if raw is not None else None
