from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_decision_log(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_last_decision_event(path: Path, event: str) -> dict[str, Any]:
    """Most recent decision_log entry for a given event type."""
    if not path.exists():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").strip().splitlines()):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") == event:
            return ev
    return {}


def get_decision_log_tails(path: Path) -> dict[str, Any]:
    """Separate last events — do not collapse bundle state into target_write_audit only."""
    return {
        "last_target_write_audit": get_last_decision_event(path, "target_write_audit") or None,
        "last_bundle_reconciliation": get_last_decision_event(path, "bundle_reconciliation") or None,
        "last_execution_decision": get_last_decision_event(path, "execution_decision") or None,
        "last_line": _read_last_decision_line(path),
    }


def _read_last_decision_line(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
