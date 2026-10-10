"""Persist compass snapshot beside economy_signal (Review-only, no target writes).

Proxy series IDs document the historical frequency calibration; live multi-asset
FRED pulls are optional and fail-open — MVP frequency is precomputed JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_system.economy_compass.compass import CompassView

CACHE_REL = Path("data") / "local" / "economy_compass.json"

# FRED (or common) proxy labels for the four sleeves — documented for operators.
PROXY_SERIES = {
    "equity": {"fred": "SP500", "note": "S&P 500 index level proxy"},
    "bonds": {"fred": "DGS10", "note": "US 10Y yield (duration proxy; not total return)"},
    "cash": {"fred": "DFF", "note": "Fed funds / cash carry proxy"},
    "gold": {"fred": "GOLDAMGBD228NLBM", "note": "LBMA gold price USD"},
}


def cache_path(root: Path) -> Path:
    return Path(root) / CACHE_REL


def compass_to_payload(view: CompassView) -> dict[str, Any]:
    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": view.stage,
        "stage_label": view.stage_label,
        "alpha_line": view.alpha_line,
        "regime_warning": view.regime_warning,
        "kr_link": view.kr_link,
        "sleeves": [
            {
                "sleeve_id": s.sleeve_id,
                "label": s.label,
                "pct": s.pct,
                "action": s.action,
                "why": s.why,
            }
            for s in view.sleeves
        ],
        "frequency": {
            "available": view.frequency.available,
            "note": view.frequency.note,
            "sources": list(view.frequency.sources),
            "cells": [
                {
                    "sleeve_id": c.sleeve_id,
                    "win_rate": c.win_rate,
                    "median_ret": c.median_ret,
                    "n_months": c.n_months,
                }
                for c in view.frequency.cells
            ],
        },
        "proxies": PROXY_SERIES,
        "target_portfolio_written": False,
    }


def save_compass_snapshot(root: Path, view: CompassView) -> Path:
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(compass_to_payload(view), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_compass_snapshot(root: Path) -> dict[str, Any] | None:
    path = cache_path(root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None
