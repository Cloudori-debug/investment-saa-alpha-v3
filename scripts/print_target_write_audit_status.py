#!/usr/bin/env python3
"""Print target write audit verification table after pipeline or from outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
OUT = ROOT / "outputs"


def main() -> int:
    from src.alpha.target_portfolio_guard import _content_hash, _read_csv_rows, evaluate_target_guard, operational_target_path, user_target_portfolio_path
    from src.alpha.target_write_audit import get_last_target_write_audit
    from src.report.execution_metrics import count_executable_actions
    from src.validation.bundle_consistency import verify_bundle_snapshot_alignment

    health = json.loads((OUT / "system_health.json").read_text(encoding="utf-8")) if (OUT / "system_health.json").exists() else {}
    final = json.loads((OUT / "final_execution_decision.json").read_text(encoding="utf-8")) if (OUT / "final_execution_decision.json").exists() else {}
    acceptance = json.loads((OUT / "acceptance_report.json").read_text(encoding="utf-8")) if (OUT / "acceptance_report.json").exists() else {}
    tg = evaluate_target_guard(DATA, OUT)
    audit = get_last_target_write_audit(OUT)
    metrics = count_executable_actions(final)
    alignment = verify_bundle_snapshot_alignment(OUT)

    op_hash = _content_hash(_read_csv_rows(operational_target_path(DATA)))
    user_hash = _content_hash(_read_csv_rows(user_target_portfolio_path(DATA))) if user_target_portfolio_path(DATA).exists() else ""

    rows = [
        ("target guard", tg.get("severity")),
        ("target_hash", op_hash[:16] + "..."),
        ("user_target_hash", user_hash[:16] + "..."),
        ("target_write_source", audit.get("target_write_source") or final.get("last_target_write_source") or "n/a"),
        ("target_write_allowed", audit.get("target_write_allowed", final.get("last_target_write_allowed", "n/a"))),
        ("restore_occurred", final.get("target_restore_occurred", False)),
        ("conflict_detected", final.get("target_guard_conflict_detected", False)),
        ("proposal_leak", tg.get("system_proposal_leak_count", 0)),
        ("changed_rows", tg.get("changed_rows", 0)),
        ("Actual Buy Allowed", metrics.get("actual_buy_allowed_count", 0)),
        ("execution_scope", final.get("execution_scope")),
        ("acceptance_overall", acceptance.get("overall")),
        ("snapshot_alignment", alignment.get("aligned")),
    ]

    print("\n| 항목 | 값 |")
    print("|------|-----|")
    for k, v in rows:
        print(f"| {k} | {v} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
