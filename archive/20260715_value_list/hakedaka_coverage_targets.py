from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_COVERAGE_TARGETS: dict[str, float] = {
    "price_coverage": 100.0,
    "ocf_coverage": 70.0,
    "fcf_coverage": 60.0,
    "debt_coverage": 70.0,
    "cash_coverage": 70.0,
    "net_cash_coverage": 60.0,
    "treasury_scan_coverage": 80.0,
}

# Informational only — no target WARN (not all tickers have buyback events).
TREASURY_INFO_METRICS = ("treasury_event_found_rate",)

LEGACY_TARGET_ALIASES = {
    "treasury_event_extraction": "treasury_scan_coverage",
}

TARGETS_FILENAME = "hakedaka_coverage_targets.json"


def ensure_coverage_targets(data_dir: Path) -> Path:
    path = data_dir / TARGETS_FILENAME
    if not path.exists():
        doc = {
            "version": "1.0",
            "description": "Hakedaka Tier H coverage targets (shadow diagnostic only)",
            "targets_pct": dict(DEFAULT_COVERAGE_TARGETS),
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_coverage_targets(data_dir: Path) -> dict[str, float]:
    path = ensure_coverage_targets(data_dir)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        targets = doc.get("targets_pct") or doc.get("targets") or {}
        merged = dict(DEFAULT_COVERAGE_TARGETS)
        for k, v in targets.items():
            key = LEGACY_TARGET_ALIASES.get(k, k)
            if key in merged or key in TREASURY_INFO_METRICS:
                try:
                    merged[key] = float(v)
                except (TypeError, ValueError):
                    continue
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_COVERAGE_TARGETS)
