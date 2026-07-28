"""Manual override ledger — recorded exceptions, not execution authority."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_COLUMNS = [
    "date",
    "target_scope",
    "system_verdict",
    "ai_validation_judgment",
    "human_decision",
    "reason",
    "review_conditions",
    "result_notes",
    "recorded_at",
]

DEFAULT_LEDGER_PATH = Path("data/manual_override_ledger.csv")


def ensure_ledger_template(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        writer.writeheader()


def load_manual_override_ledger(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def append_manual_override(
    path: Path,
    *,
    date: str,
    target_scope: str,
    system_verdict: str,
    ai_validation_judgment: str,
    human_decision: str,
    reason: str,
    review_conditions: str = "",
    result_notes: str = "",
) -> dict[str, str]:
    """Append a recorded manual exception — does not alter execution permissions."""
    ensure_ledger_template(path)
    row = {
        "date": date,
        "target_scope": target_scope,
        "system_verdict": system_verdict,
        "ai_validation_judgment": ai_validation_judgment,
        "human_decision": human_decision,
        "reason": reason,
        "review_conditions": review_conditions,
        "result_notes": result_notes,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        writer.writerow(row)
    return row


def ledger_summary_for_report(rows: list[dict[str, str]], *, as_of: str) -> dict[str, Any]:
    recent = [r for r in rows if str(r.get("date", ""))[:10] <= as_of[:10]][-5:]
    return {
        "total_entries": len(rows),
        "recent_entries": recent,
        "note": "Ledger records human review/pilot decisions — not automatic execution authority.",
    }
