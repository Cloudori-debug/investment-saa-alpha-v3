"""Compass judgment log — append-only archive for calibration (not a trading gate)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.compass.economic_phase import _kospi_drawdown_pct, _kospi_vs_ma200_pct
from src.compass.models import CompassResult
from src.decision_logger import append_decision_log
from src.models import MarketIndicators

JUDGMENT_LOG_NAME = "compass_judgment_log.jsonl"


def judgment_log_path(output_dir: Path) -> Path:
    return output_dir / JUDGMENT_LOG_NAME


def read_judgment_log_tail(path: Path, n: int = 20) -> list[dict[str, Any]]:
    if n <= 0 or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _market_inputs(market: MarketIndicators) -> dict[str, Any]:
    dd = _kospi_drawdown_pct(market)
    vs_ma = _kospi_vs_ma200_pct(market)
    return {
        "vix": market.vix,
        "kospi_drawdown_pct": None if dd is None else round(dd, 4),
        "kospi_vs_ma200_pct": None if vs_ma is None else round(vs_ma, 4),
        "korea_10y": market.korea_10y,
        "usdkrw": market.usdkrw,
        "oil_brent": market.oil_brent,
        "foreign_flow_3d": market.foreign_flow_3d,
    }


def write_compass_judgment_log(
    output_dir: Path,
    compass: CompassResult,
    market: MarketIndicators,
    *,
    tilt_meta: dict[str, Any] | None = None,
    run_id: str = "",
) -> Path:
    """Append one judgment row. Read-only archive — execution must not gate on this file."""
    meta = tilt_meta or {}
    computed_phase = compass.computed_market_phase or compass.market_phase
    entry: dict[str, Any] = {
        "date": compass.date[:10],
        "run_id": run_id or compass.date,
        "growth_score": compass.growth_score,
        "inflation_score": compass.inflation_score,
        "liquidity_score": compass.liquidity_score,
        "risk_appetite_score": compass.risk_appetite_score,
        "market_phase": compass.market_phase.value,
        "computed_market_phase": computed_phase.value,
        "phase_confidence": compass.phase_confidence,
        "computed_regime": compass.computed_regime.value,
        "applied_regime": compass.applied_regime.value,
        "regime_confidence": compass.regime_confidence,
        "override_active": bool(compass.override.active),
        "compass_direction": compass.compass_direction,
        "taa_tilt_scale": meta.get("taa_tilt_scale", 1.0),
        "raw_phase_tilt": meta.get("raw_phase_tilt") or {},
        "raw_regime_tilt": meta.get("raw_regime_tilt") or {},
        "scaled_phase_tilt": meta.get("scaled_phase_tilt") or {},
        "scaled_regime_tilt": meta.get("scaled_regime_tilt") or {},
        "market_inputs": _market_inputs(market),
    }
    path = judgment_log_path(output_dir)
    append_decision_log(path, entry)
    return path
