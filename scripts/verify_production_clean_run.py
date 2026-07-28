#!/usr/bin/env python3
"""Production 2-run clean run verification for target_portfolio_guard idempotency."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tg_detail(doc: dict[str, Any]) -> dict[str, Any]:
    for chk in doc.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            return chk.get("detail") or {}
    for item in doc.get("items") or []:
        if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
            return item.get("detail") or {}
    hr = doc.get("health_report") or {}
    for chk in hr.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            return chk.get("detail") or {}
    return {}


def collect_metrics(label: str) -> dict[str, Any]:
    from src.alpha.target_portfolio_guard import (
        _content_hash,
        _read_csv_rows,
        operational_target_path,
        operational_tickers_not_in_user,
        user_target_portfolio_path,
    )
    from src.report.execution_metrics import count_executable_actions
    from src.validation.bundle_consistency import verify_bundle_snapshot_alignment

    health = _read_json(OUT / "system_health.json")
    acceptance = _read_json(OUT / "acceptance_report.json")
    bundle = _read_json(OUT / "ai_export_bundle.json")
    final = _read_json(OUT / "final_execution_decision.json")
    manifest = _read_json(OUT / "run_manifest.json")

    tg = _tg_detail(health)
    op_hash = _content_hash(_read_csv_rows(operational_target_path(DATA)))
    user_hash = _content_hash(_read_csv_rows(user_target_portfolio_path(DATA))) if user_target_portfolio_path(DATA).exists() else ""

    # restore / audit from this run's decision_log
    restore_occurred = False
    conflict_detected = bool(final.get("target_guard_conflict_detected"))
    recon_event: dict[str, Any] = {}
    write_audit_events: list[dict[str, Any]] = []
    blocked_writes = 0
    run_id = manifest.get("run_id")
    log_path = OUT / "decision_log.jsonl"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if run_id and ev.get("run_id") != run_id:
                continue
            if ev.get("event") == "target_restore":
                restore_occurred = True
            if ev.get("event") == "target_write_audit":
                write_audit_events.append(ev)
                if ev.get("target_write_allowed") is False:
                    blocked_writes += 1
            if ev.get("event") == "bundle_reconciliation":
                recon_event = ev
                restore_occurred = restore_occurred or bool(ev.get("restore_occurred"))
                conflict_detected = conflict_detected or bool(ev.get("conflict_detected"))

    if write_audit_events:
        allowed_writes = [e for e in write_audit_events if e.get("target_write_allowed")]
        target_write_source = allowed_writes[-1].get("target_write_source") if allowed_writes else "blocked_only"
    else:
        target_write_source = "n/a"

    alignment = verify_bundle_snapshot_alignment(OUT)
    metrics = count_executable_actions(final)
    op_text = operational_target_path(DATA).read_text(encoding="utf-8")

    return {
        "label": label,
        "run_id": manifest.get("run_id"),
        "guard_severity": tg.get("severity", "—"),
        "guard_status": tg.get("status", "—"),
        "target_hash": op_hash,
        "user_target_hash": user_hash or tg.get("user_target_hash", ""),
        "health_snapshot_id": health.get("health_snapshot_id") or health.get("meta", {}).get("health_snapshot_id", ""),
        "acceptance_snapshot_id": acceptance.get("health_snapshot_id", ""),
        "bundle_snapshot_id": (bundle.get("health_report") or {}).get("health_snapshot_id", bundle.get("health_snapshot_id", "")),
        "changed_rows": tg.get("changed_rows", "—"),
        "proposal_leak": tg.get("system_proposal_leak_count", "—"),
        "material": tg.get("unknown_material_count", "—"),
        "has_030190": "030190" in op_text,
        "restore_occurred": restore_occurred,
        "conflict_detected": conflict_detected,
        "snapshot_alignment": alignment.get("aligned"),
        "actual_buy_allowed": metrics.get("actual_buy_allowed_count", 0),
        "execution_scope": final.get("execution_scope") or acceptance.get("execution_scope"),
        "system_status": final.get("system_status"),
        "health_overall": health.get("overall"),
        "acceptance_overall": acceptance.get("overall"),
        "recon_event": recon_event,
        "target_write_source": target_write_source,
        "write_audit_events": write_audit_events,
        "blocked_writes": blocked_writes,
    }


def run_pipeline() -> None:
    print("Running full_pipeline (--no-backtest)...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "src.main", "--no-backtest"],
        cwd=ROOT,
        check=True,
    )


def pass_criteria(m1: dict[str, Any], m2: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for i, m in enumerate((m1, m2), start=1):
        prefix = f"Run{i}"
        if m.get("guard_severity") != "PASS":
            failures.append(f"{prefix}: guard severity != PASS ({m.get('guard_severity')})")
        if m.get("restore_occurred"):
            failures.append(f"{prefix}: restore_occurred=True (clean run fail)")
        if m.get("conflict_detected"):
            failures.append(f"{prefix}: conflict_detected=True")
        if not m.get("snapshot_alignment"):
            failures.append(f"{prefix}: snapshot_alignment=False")
        if m.get("actual_buy_allowed", 0) != 0:
            failures.append(f"{prefix}: Actual Buy Allowed != 0")
        if m.get("has_030190"):
            failures.append(f"{prefix}: 030190 in operational target")
        if m.get("changed_rows") not in (0, "0", "—") and m.get("changed_rows"):
            if int(m.get("changed_rows") or 0) != 0:
                failures.append(f"{prefix}: changed_rows != 0")
        if int(m.get("proposal_leak") or 0) != 0:
            failures.append(f"{prefix}: proposal_leak != 0")
        if int(m.get("material") or 0) != 0:
            failures.append(f"{prefix}: material != 0")
        if m.get("acceptance_overall") != "YELLOW":
            failures.append(f"{prefix}: acceptance_overall != YELLOW ({m.get('acceptance_overall')})")
        if m.get("execution_scope") != "ETF_ONLY":
            failures.append(f"{prefix}: execution_scope != ETF_ONLY ({m.get('execution_scope')})")
        if m.get("blocked_writes", 0) > 0:
            failures.append(f"{prefix}: unauthorized target write blocked ({m.get('blocked_writes')})")
        src = m.get("target_write_source")
        if src not in ("n/a", "no_write", None) and m.get("blocked_writes", 0) == 0:
            allowed_during_clean = src in ("restore_from_user_target",)
            if allowed_during_clean:
                failures.append(f"{prefix}: target write during clean run ({src})")

    if m1.get("target_hash") != m2.get("target_hash"):
        failures.append(f"target_hash differs: {m1.get('target_hash')[:12]} vs {m2.get('target_hash')[:12]}")
    if m1.get("user_target_hash") != m2.get("user_target_hash"):
        failures.append("user_target_hash differs between runs")

    return not failures, failures


def print_table(m1: dict[str, Any], m2: dict[str, Any]) -> None:
    keys = [
        "run_id", "guard_severity", "target_hash", "user_target_hash",
        "health_snapshot_id", "changed_rows", "proposal_leak", "material",
        "has_030190", "restore_occurred", "conflict_detected",
        "target_write_source", "blocked_writes",
        "snapshot_alignment", "actual_buy_allowed", "execution_scope",
        "health_overall", "acceptance_overall",
    ]
    print("\n| 항목 | Run 1 | Run 2 |")
    print("|------|-------|-------|")
    for k in keys:
        v1 = m1.get(k, "—")
        v2 = m2.get(k, "—")
        if k in ("target_hash", "user_target_hash") and isinstance(v1, str) and len(v1) > 12:
            v1, v2 = v1[:12] + "…", v2[:12] + "…"
        print(f"| {k} | {v1} | {v2} |")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    run_pipeline()
    m1 = collect_metrics("run1")
    run_pipeline()
    m2 = collect_metrics("run2")

    print_table(m1, m2)
    ok, failures = pass_criteria(m1, m2)
    hard_failures = failures

    print("\n### Run 1 bundle_reconciliation")
    print(json.dumps(m1.get("recon_event") or {}, ensure_ascii=False, indent=2))
    print("\n### Run 2 bundle_reconciliation")
    print(json.dumps(m2.get("recon_event") or {}, ensure_ascii=False, indent=2))

    print("\n### Audit log summary")
    for label, m in [("Run 1", m1), ("Run 2", m2)]:
        writes = m.get("write_audit_events") or []
        print(f"- {label}: target_write_source={m.get('target_write_source')}, "
              f"write_audit_events={len(writes)}, blocked={m.get('blocked_writes', 0)}, "
              f"bundle_reconciliation={'yes' if m.get('recon_event') else 'no'}")

    if hard_failures:
        print("\n[CLEAN RUN FAIL]")
        for f in hard_failures:
            print(f"  - {f}")
        return 1

    print("\n[CLEAN RUN PASS] target hash idempotent, restore 없음, guard PASS, Buy 0")
    if m1.get("health_snapshot_id") != m2.get("health_snapshot_id"):
        print("  (note: health_snapshot_id는 run_id 포함 — run 간 동일 기대 아님, run 내부 alignment만 검증)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
