from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.data_refresh.external_market import business_days_between

TIER_B_STATE_FILE = "tier_b_refresh.json"
DEFAULT_INTERVAL_BUSINESS_DAYS = 5


@dataclass
class TierBRefreshResult:
    as_of: str
    ran: bool
    reason: str
    prices_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _state_path(data_dir: Path) -> Path:
    return data_dir / TIER_B_STATE_FILE


def load_tier_b_state(data_dir: Path) -> dict:
    path = _state_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def tier_b_is_due(
    data_dir: Path,
    as_of: str,
    *,
    interval_business_days: int = DEFAULT_INTERVAL_BUSINESS_DAYS,
) -> bool:
    state = load_tier_b_state(data_dir)
    last = str(state.get("last_run_date", "")).strip()
    if not last:
        return True
    return business_days_between(last, as_of[:10]) >= interval_business_days


def write_tier_b_state(data_dir: Path, as_of: str, *, prices_count: int) -> Path:
    path = _state_path(data_dir)
    payload = {
        "last_run_date": as_of[:10],
        "last_run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prices_count": prices_count,
        "scope": "liquid",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_tier_b_if_due(
    data_dir: Path,
    *,
    as_of: str,
    force: bool = False,
    interval_business_days: int = DEFAULT_INTERVAL_BUSINESS_DAYS,
) -> TierBRefreshResult:
    """Tier B — liquid pool 주간 bulk merge (기본 5영업일 간격)."""
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return TierBRefreshResult(as_of=as_of, ran=False, reason="pytest_skip")

    if not force and not tier_b_is_due(data_dir, as_of, interval_business_days=interval_business_days):
        state = load_tier_b_state(data_dir)
        return TierBRefreshResult(
            as_of=as_of,
            ran=False,
            reason=f"not_due (last={state.get('last_run_date', '—')})",
        )

    try:
        from src.data_refresh.pykrx_bulk import run_pykrx_bulk_collect

        bulk = run_pykrx_bulk_collect(
            data_dir,
            as_of=as_of,
            scope="liquid",
            write_history=True,
            enrich_dart=False,
        )
        write_tier_b_state(data_dir, as_of, prices_count=bulk.prices_count)
        return TierBRefreshResult(
            as_of=as_of,
            ran=True,
            reason="liquid_bulk_ok",
            prices_count=bulk.prices_count,
            warnings=list(bulk.warnings),
        )
    except Exception as exc:
        return TierBRefreshResult(
            as_of=as_of,
            ran=False,
            reason=f"bulk_failed: {exc}",
            warnings=[str(exc)],
        )
