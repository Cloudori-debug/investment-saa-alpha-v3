from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.data_loader import load_positions
from src.models import PositionRow

EXECUTION_AUTHORITY = "v1.0.2"
WEIGHT_SUM_TOLERANCE = 0.05

CORE_REFERENCE_DISCLAIMER = (
    "Core SAA benchmark reference (14-slot framework). Drives target structure via "
    "absolute_return_policy; does not hold direct execution authority (v1.0.2 gated)."
)


class CoreSaaReferenceValidationError(Exception):
    """Core reference YAML failed mandatory shadow guardrails."""


def validate_core_saa_reference(doc: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). errors → loader reject."""
    errors: list[str] = []
    warnings: list[str] = []

    if doc.get("status") not in ("shadow_reference_only", "primary_absolute_return_benchmark"):
        errors.append("status must be shadow_reference_only or primary_absolute_return_benchmark")
    authority = doc.get("authority")
    if authority not in ("none", "benchmark"):
        errors.append("authority must be none or benchmark")
    for key in ("affects_target_portfolio", "affects_trade_actions", "affects_execution_scope"):
        if doc.get(key) is not False:
            errors.append(f"{key} must be false")

    assets = doc.get("assets") or []
    weight_sum = 0.0
    unresolved = 0
    tradable_count = 0

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        tw = asset.get("target_weight_pct")
        if tw is not None:
            weight_sum += float(tw)
        mapping = str(asset.get("mapping_status") or "resolved")
        ticker = asset.get("ticker")
        if mapping == "unresolved" or ticker is None:
            unresolved += 1
            warnings.append(f"unresolved ticker: {asset.get('name', '?')}")
        if asset.get("tradable") is True and ticker:
            tradable_count += 1

    if abs(weight_sum - 100.0) > WEIGHT_SUM_TOLERANCE:
        warnings.append(f"target_weight_pct sum {weight_sum:.2f} != 100 (tolerance {WEIGHT_SUM_TOLERANCE})")

    expected_slots = doc.get("reference_slot_count")
    if expected_slots is not None and len(assets) != int(expected_slots):
        warnings.append(f"reference_slot_count {expected_slots} != assets length {len(assets)}")

    return errors, warnings


def load_core_saa_reference(data_dir: Path) -> dict[str, Any] | None:
    path = data_dir / "core_saa_reference.yaml"
    if not path.exists():
        return None
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors, warnings = validate_core_saa_reference(doc)
    if errors:
        return None
    doc["_validation_warnings"] = warnings
    return doc


def _normalize_ticker(ticker: str | None) -> str | None:
    if ticker is None:
        return None
    t = str(ticker).strip().upper()
    if not t or t == "NULL":
        return None
    return t if t == "CASH" else t.zfill(6) if t.isdigit() else t


def _portfolio_weights(positions: list[PositionRow]) -> tuple[float, dict[str, float]]:
    total = sum(float(p.current_value or 0) for p in positions) or 0.0
    if total <= 0:
        return 0.0, {}
    weights = {
        _normalize_ticker(p.ticker) or "": round(float(p.current_value or 0) / total * 100, 2)
        for p in positions
    }
    weights.pop("", None)
    return total, weights


def _asset_row(
    asset: dict[str, Any],
    weights: dict[str, float],
) -> dict[str, Any]:
    ticker_raw = asset.get("ticker")
    ticker = _normalize_ticker(ticker_raw)
    target = float(asset.get("target_weight_pct") or 0)
    current = weights.get(ticker, 0.0) if ticker else 0.0
    gap = round(current - target, 2)
    tradable = bool(asset.get("tradable", ticker is not None))
    mapping = str(asset.get("mapping_status") or ("resolved" if ticker else "unresolved"))

    return {
        "ticker": ticker,
        "name": asset.get("name", ""),
        "role": asset.get("role", ""),
        "sleeve": asset.get("sleeve", ""),
        "core_target_weight_pct": target,
        "current_weight_pct": current,
        "gap_pct": gap,
        "tradable": tradable,
        "mapping_status": mapping,
        "in_portfolio": current > 0,
        "note": asset.get("note", ""),
    }


def build_core_saa_reference_diagnostic(
    data_dir: Path,
    *,
    as_of: str = "",
) -> dict[str, Any] | None:
    """Core target vs current — shadow gap only. target/trade_actions 미변경."""
    ref = load_core_saa_reference(data_dir)
    if not ref:
        return None

    positions = load_positions(data_dir / "positions.csv")
    total_nav, weights = _portfolio_weights(positions)
    assets = [a for a in (ref.get("assets") or []) if isinstance(a, dict)]

    core_rows = [_asset_row(a, weights) for a in assets]
    resolved_tickers = {
        r["ticker"] for r in core_rows if r.get("ticker")
    }

    missing_core = [r for r in core_rows if r["current_weight_pct"] <= 0 and r["core_target_weight_pct"] > 0]
    non_core_held: list[dict[str, Any]] = []

    satellite_path = data_dir / "target_portfolio.csv"
    satellite_tickers: set[str] = set()
    if satellite_path.exists():
        import csv

        with satellite_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                t = _normalize_ticker(row.get("ticker", ""))
                if t and t != "CASH":
                    satellite_tickers.add(t)

    for pos in positions:
        t = _normalize_ticker(pos.ticker)
        if not t or t == "CASH":
            continue
        w = weights.get(t, 0.0)
        if t not in resolved_tickers and w > 0:
            non_core_held.append({
                "ticker": t,
                "name": pos.name,
                "asset_group": pos.asset_group,
                "current_weight_pct": w,
                "in_satellite_target": t in satellite_tickers,
                "note": "kr_alpha or Satellite-only — not in Core reference",
            })

    target_sum = round(sum(r["core_target_weight_pct"] for r in core_rows), 2)
    current_core_sum = round(sum(r["current_weight_pct"] for r in core_rows), 2)
    held_count = sum(1 for r in core_rows if r["in_portfolio"])
    tradable_count = sum(1 for a in assets if a.get("tradable") is True and a.get("ticker"))
    unresolved_count = sum(
        1 for a in assets
        if a.get("mapping_status") == "unresolved" or a.get("ticker") is None
    )

    sleeve_target: dict[str, float] = {}
    sleeve_current: dict[str, float] = {}
    for r in core_rows:
        sleeve = str(r.get("sleeve") or "other")
        sleeve_target[sleeve] = round(sleeve_target.get(sleeve, 0) + r["core_target_weight_pct"], 2)
        if r["current_weight_pct"] > 0:
            sleeve_current[sleeve] = round(sleeve_current.get(sleeve, 0) + r["current_weight_pct"], 2)

    validation_warnings = list(ref.get("_validation_warnings") or [])

    return {
        "mode": ref.get("benchmark_mode") or "benchmark_reference_only",
        "authority": ref.get("authority") or "benchmark",
        "diagnostic_only": True,
        "execution_authority": EXECUTION_AUTHORITY,
        "as_of": as_of,
        "basis": ref.get("basis", "user_long_term_core_saa"),
        "schema_version": ref.get("schema_version", "core_saa_reference.v0.2"),
        "reference_slot_count": ref.get("reference_slot_count", len(assets)),
        "tradable_etf_count": tradable_count,
        "note": CORE_REFERENCE_DISCLAIMER,
        "validation_warnings": validation_warnings,
        "summary": {
            "core_target_weight_sum_pct": target_sum,
            "core_current_weight_sum_pct": current_core_sum,
            "core_gap_sum_pct": round(current_core_sum - target_sum, 2),
            "core_reference_count": len(core_rows),
            "core_held_count": held_count,
            "core_missing_count": len(missing_core),
            "unresolved_ticker_count": unresolved_count,
            "non_core_held_count": len(non_core_held),
            "total_nav_krw": int(total_nav),
        },
        "sleeve_target_pct": dict(sorted(sleeve_target.items(), key=lambda x: -x[1])),
        "sleeve_current_pct": dict(sorted(sleeve_current.items(), key=lambda x: -x[1])),
        "core_assets": core_rows,
        "missing_core": missing_core,
        "non_core_holdings": sorted(non_core_held, key=lambda x: -x["current_weight_pct"]),
        "report_lines": [
            f"Core reference (shadow): target {target_sum}% · current {current_core_sum}% · "
            f"held {held_count}/{len(core_rows)}",
            f"Unresolved tickers: {unresolved_count} · Non-Core holdings: {len(non_core_held)}",
            "authority: none — diagnostic_only — no trade_actions impact",
        ],
    }


def write_core_saa_reference_diagnostic(doc: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
