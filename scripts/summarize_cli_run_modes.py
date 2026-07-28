#!/usr/bin/env python3
"""Summarize CLI 4-mode clean run from saved runtime_profile snapshots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATA = ROOT / "data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _target_guard() -> str:
    health = _read(OUT / "system_health.json")
    for chk in health.get("checks") or []:
        if chk.get("name") == "target_portfolio_guard":
            return str(chk.get("status") or (chk.get("detail") or {}).get("severity") or "unknown").lower()
    return "unknown"


def _target_write_count_for_run(run_id: str | None) -> int:
    if not run_id:
        return 0
    n = 0
    p = OUT / "target_write_audit.jsonl"
    if not p.exists():
        return 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ev = json.loads(line)
            if ev.get("run_id") == run_id and ev.get("target_write_allowed") is True:
                n += 1
    return n


def _actual_buy() -> int:
    from src.report.execution_metrics import count_executable_actions

    return int(count_executable_actions(_read(OUT / "final_execution_decision.json")).get("actual_buy_allowed_count") or 0)


def main() -> int:
    diag = _read(OUT / "no_action_diagnostics.json")
    tg = _target_guard()
    ab = _actual_buy()

    modes = ["quick", "standard", "deep", "bundle_only"]
    rows = []
    all_ok = True
    for mode in modes:
        prof = _read(OUT / f"runtime_profile_{mode}.json")
        if not prof:
            prof = _read(OUT / "runtime_profile.json") if _read(OUT / "runtime_profile.json").get("run_mode") == mode else {}
        slowest = (prof.get("slowest_steps") or [{}])[0].get("step", "—")
        steps = prof.get("step_timings") or {}
        run_id = str(prof.get("run_id") or "")
        tw = _target_write_count_for_run(run_id)
        errs = []
        if prof.get("entrypoint") != "cli":
            errs.append("entrypoint!=cli")
        if prof.get("run_mode") != mode:
            errs.append(f"run_mode={prof.get('run_mode')}")
        if tg not in {"pass", "ok"}:
            errs.append(f"target_guard={tg}")
        if tw != 0:
            errs.append(f"target_write={tw}")
        if ab != 0:
            errs.append(f"actual_buy={ab}")
        if mode == "quick":
            if prof.get("pykrx_call_count", 0) != 0:
                errs.append("pykrx>0")
            if "pipeline_core" in steps:
                errs.append("ran pipeline_core")
        if mode == "deep":
            if "kosdaq_universe_sync" not in steps and "data_hooks" not in steps:
                errs.append("no kosdaq/data_hooks")
            if float(prof.get("bundle_size_mb") or 0) <= 0:
                errs.append("no bundle")
        if mode == "bundle_only":
            if "pipeline_core" in steps:
                errs.append("ran pipeline_core")
        verdict = "PASS" if prof and not errs else "FAIL"
        if verdict == "FAIL":
            all_ok = False
        rows.append({
            "run_mode": mode,
            "exit_code": 0 if prof else -1,
            "total_seconds": prof.get("total_seconds"),
            "slowest_step": slowest,
            "target_guard": tg,
            "target_write_count": tw,
            "actual_buy_allowed": ab,
            "no_action_expected": diag.get("no_action_is_expected"),
            "pykrx_call_count": prof.get("pykrx_call_count"),
            "cache_hit_count": prof.get("cache_hit_count"),
            "cache_miss_count": prof.get("cache_miss_count"),
            "bundle_size_mb": prof.get("bundle_size_mb"),
            "generated_files_count": prof.get("generated_files_count"),
            "verdict": verdict,
            "errors": errs,
        })

    cols = [
        "run_mode", "exit_code", "total_seconds", "slowest_step", "target_guard",
        "target_write_count", "actual_buy_allowed", "no_action_expected",
        "pykrx_call_count", "cache_hit_count", "cache_miss_count",
        "bundle_size_mb", "generated_files_count", "verdict",
    ]
    print("=== CLI 4-MODE CLEAN RUN SUMMARY ===")
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r.get(c, "")) for c in cols))
    print()
    print("공통:", f"target_guard={tg}", f"actual_buy_allowed={ab}")
    print("no_action_is_expected:", diag.get("no_action_is_expected"))
    print("status_alignment_pass:", diag.get("status_alignment_pass"))
    print("OVERALL:", "PASS" if all_ok else "FAIL")
    for r in rows:
        if r["errors"]:
            print(f"  {r['run_mode']}: {r['errors']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
