from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models import MarketIndicators, TriggerStatus
from src.trigger_engine import _pct_drawdown


def build_kospi_trigger_reviews(
    market: MarketIndicators,
    rules: dict,
    *,
    core_price_gate: str = "pass",
    data_gate: str = "GREEN",
    health_gate: str = "GREEN",
    dry_run_days: int = 0,
) -> list[dict[str, Any]]:
    cfg = rules.get("kospi_drawdown_triggers") or {}
    if not cfg:
        return []

    kospi_dd = _pct_drawdown(market.kospi, market.kospi_recent_high)
    if kospi_dd is None:
        return []

    req = cfg.get("require") or {}
    blocked_regimes = [r.upper() for r in (req.get("manual_regime_block") or [])]
    regime_upper = (market.regime or "").upper()
    gated_reasons: list[str] = []
    if core_price_gate != str(req.get("core_price_gate", "pass")):
        gated_reasons.append(f"core_price_gate={core_price_gate}")
    if data_gate == str(req.get("data_gate_not", "RED")):
        gated_reasons.append(f"data_gate={data_gate}")
    if health_gate == str(req.get("health_gate_not", "RED")):
        gated_reasons.append(f"health_gate={health_gate}")
    min_dry = int(req.get("dry_run_days_min", 10))
    if dry_run_days < min_dry:
        gated_reasons.append(f"dry_run_days {dry_run_days}/{min_dry}")
    if any(b in regime_upper for b in blocked_regimes):
        gated_reasons.append("manual_regime blocked")

    gates_ok = not gated_reasons
    reviews: list[dict[str, Any]] = []

    for level in sorted(cfg.get("levels") or [], key=lambda x: float(x.get("threshold_pct", 0))):
        threshold = float(level.get("threshold_pct", 0))
        signal = kospi_dd <= threshold
        if not signal:
            continue
        reviews.append({
            "trigger_id": level.get("name", ""),
            "signal_detected": True,
            "drawdown_pct": kospi_dd,
            "threshold_pct": threshold,
            "review_status": "WATCH" if gates_ok else "GATED",
            "execution_status": "REVIEW_ONLY" if gates_ok else "INACTIVE",
            "gated_reasons": [] if gates_ok else gated_reasons,
            "action": level.get("action", ""),
            "execution": level.get("execution", "manual_review_only"),
        })

    if not reviews and kospi_dd is not None:
        reviews.append({
            "trigger_id": "KOSPI_PULLBACK_NONE",
            "signal_detected": False,
            "drawdown_pct": kospi_dd,
            "review_status": "INACTIVE",
            "execution_status": "INACTIVE",
            "gated_reasons": [],
            "action": None,
            "execution": "manual_review_only",
        })

    return reviews


def write_trigger_reviews(path: Path, reviews: list[dict[str, Any]], *, as_of: str) -> None:
    doc = {
        "schema_version": "1.0",
        "as_of": as_of,
        "kospi_drawdown_reviews": reviews,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
