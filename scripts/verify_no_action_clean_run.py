#!/usr/bin/env python3
"""Verify no_action_diagnostics clean run criteria."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs"
DATA = ROOT / "data"


def read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))

    nap = OUT / "no_action_diagnostics.json"
    ok("1 no_action_diagnostics.json", nap.exists())
    diag = read(nap)

    ok("2 no_action_is_expected=true", diag.get("no_action_is_expected") is True, str(diag.get("no_action_is_expected")))
    ok("3 primary_blockers present", bool(diag.get("primary_blockers")))
    ok("3 secondary_blockers present", bool(diag.get("secondary_blockers")))
    ok("4 status_alignment_pass=true", diag.get("status_alignment_pass") is True, json.dumps(diag.get("status_alignment"), ensure_ascii=False))
    ok("6 gate_detail_complete=true", diag.get("gate_detail_complete") is True)

    acc = read(OUT / "acceptance_report.json")
    items = {i.get("id"): i for i in acc.get("items", []) if isinstance(i, dict)}
    for ac_id in ("AC-02", "AC-03"):
        item = items.get(ac_id, {})
        detail = item.get("detail") or {}
        msg = str(item.get("message") or "")
        is_red = detail.get("gate") == "RED" or "gate=RED" in msg
        if is_red:
            ok(f"7/8 {ac_id} fail_reasons", bool(detail.get("fail_reasons")), str(detail.get("fail_reasons", [])[:3]))
            ok(f"7/8 {ac_id} detail non-empty", bool(detail), str(list(detail.keys())[:6]))
        else:
            ok(f"7/8 {ac_id} documented", bool(detail) or bool(msg), msg)

    trace = diag.get("actual_buy_trace") or {}
    ok("9 final_actual_buy_allowed=0", trace.get("final_actual_buy_allowed") == 0, str(trace.get("final_actual_buy_allowed")))

    cf = diag.get("counterfactual_results") or {}
    ok("10 counterfactual_results exists", bool(cf))

    manifest = read(OUT / "run_manifest.json")
    run_id = manifest.get("run_id")
    target_writes = 0
    cf_events = 0
    log_path = OUT / "decision_log.jsonl"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if run_id and ev.get("run_id") != run_id:
                continue
            if ev.get("event") == "target_write_audit" and ev.get("target_write_allowed") is True:
                target_writes += 1
            if "counterfactual" in str(ev.get("event", "")).lower():
                cf_events += 1
    ok("10 no counterfactual in decision_log", cf_events == 0, f"cf_events={cf_events}")
    ok("11 target_write_count=0", target_writes == 0, str(target_writes))

    health = read(OUT / "system_health.json")
    tg_status = "unknown"
    tg_detail: dict = {}
    for c in health.get("checks", []):
        if c.get("name") == "target_portfolio_guard":
            tg_status = str(c.get("status"))
            tg_detail = c.get("detail") or {}
    ok("12 target_guard PASS", tg_status == "pass" or tg_detail.get("severity") == "PASS", tg_status)

    hash_match = (
        tg_detail.get("target_hash") == tg_detail.get("user_target_hash")
        or tg_detail.get("current_hash") == tg_detail.get("user_target_hash")
    )
    ok("13 target_hash=user_target_hash", hash_match, f"{tg_detail.get('current_hash')} vs {tg_detail.get('user_target_hash')}")

    ok("14 daily_report.md", (OUT / "daily_report.md").exists())
    ok("14 ai_export_bundle.json", (OUT / "ai_export_bundle.json").exists())

    clarity = read(OUT / "report_clarity_validation.json")
    ok("15 report_clarity pass", clarity.get("pass") is True, str(clarity.get("failures", [])[:5]))

    brief = read(OUT / "daily_brief.json")
    v2 = read(OUT / "alpha_v2_summary.json")
    auth_scope = trace.get("authoritative_execution_scope") or (diag.get("status_alignment") or {}).get("authoritative_execution_scope")
    acc_scope = acc.get("execution_scope")
    brief_scope = (brief.get("system_status") or {}).get("execution_scope")
    v2_scope = (v2.get("execution_context") or {}).get("execution_scope")

    from src.report.execution_metrics import count_executable_actions

    final = read(OUT / "final_execution_decision.json")
    metrics = count_executable_actions(final)

    print("=== CLEAN RUN VERIFICATION ===")
    for name, passed, detail in checks:
        mark = "PASS" if passed else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" | {detail}"
        print(line)

    print()
    print("=== SUMMARY OUTPUT ===")
    print("no_action_is_expected:", diag.get("no_action_is_expected"))
    print("primary_blockers:", diag.get("primary_blockers"))
    print("secondary_blockers:", diag.get("secondary_blockers"))
    print("status_alignment_pass:", diag.get("status_alignment_pass"))
    print("status_alignment:", json.dumps(diag.get("status_alignment"), ensure_ascii=False))
    print("gate_detail_complete:", diag.get("gate_detail_complete"))
    print("final_actual_buy_allowed:", trace.get("final_actual_buy_allowed"))
    print("counterfactual would_open_buy_path:")
    for k, v in cf.items():
        if isinstance(v, dict):
            print(f"  {k}:", v.get("would_open_buy_path"))
    print("recommended_fix:", diag.get("recommended_fix"))
    print("target_write_count:", target_writes)
    print("execution_scope acceptance:", acc_scope)
    print("execution_scope authoritative:", auth_scope)
    print("execution_scope daily_brief:", brief_scope)
    print("execution_scope alpha_v2:", v2_scope)
    print("Actual Buy Allowed:", metrics.get("actual_buy_allowed_count"))
    print("report_clarity failures:", clarity.get("failures"))
    print("system_error_likely:", diag.get("system_error_likely"))
    all_pass = all(p for _, p, _ in checks)
    print("OVERALL:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
