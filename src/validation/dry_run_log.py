from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


def make_run_id() -> str:
    """로컬 ISO run_id (KST +09:00 근사)."""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def write_run_manifest(
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    source_outputs: list[str],
) -> Path:
    path = output_dir / "run_manifest.json"
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "as_of": as_of,
        "source_outputs": source_outputs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def append_dry_run_log(
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    data_gate: str,
    portfolio_gate: str | None,
    alpha_gate: str | None,
    applied_regime: str | None,
    computed_regime: str | None,
    override_active: bool,
    action_count: int,
    alpha_candidate_count: int,
    trigger_active: list[str],
    overall_status: str | None = None,
    execution_scope: str | None = None,
    alpha_approval: str | None = None,
    buy_allowed_count: int = 0,
    kr_alpha_wait_count: int = 0,
    market_stale_max_days: int | None = None,
    override_age_days: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = output_dir / "dry_run_log.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    kst = timezone(timedelta(hours=9))
    entry: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(kst).isoformat(timespec="seconds"),
        "date": as_of,
        "overall_status": overall_status,
        "execution_scope": execution_scope,
        "alpha_approval": alpha_approval,
        "data_gate": data_gate,
        "portfolio_gate": portfolio_gate,
        "alpha_gate": alpha_gate,
        "applied_regime": applied_regime,
        "computed_regime": computed_regime,
        "override_active": override_active,
        "action_count": action_count,
        "alpha_candidates": alpha_candidate_count,
        "triggers_active": trigger_active,
        "buy_allowed_count": buy_allowed_count,
        "kr_alpha_wait_count": kr_alpha_wait_count,
    }
    if market_stale_max_days is not None:
        entry["market_stale_max_days"] = market_stale_max_days
    if override_age_days is not None:
        entry["override_age_days"] = override_age_days
    if extra:
        entry.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def load_dry_run_summary(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "dry_run_log.jsonl"
    if not path.exists():
        return {"days": 0, "entries": [], "dates": []}
    entries = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    dates = sorted({e.get("date") for e in entries if e.get("date")})
    return {"days": len(dates), "entries": entries, "dates": dates}
