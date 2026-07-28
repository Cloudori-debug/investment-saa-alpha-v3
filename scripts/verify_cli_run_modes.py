#!/usr/bin/env python3
"""CLI 4-mode clean run verification — quick / standard / deep / bundle_only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
PYTHON = sys.executable


@dataclass
class ModeResult:
    run_mode: str
    exit_code: int = -1
    elapsed_sec: float = 0.0
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    passed: bool = False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _target_guard_status() -> tuple[str, dict[str, Any]]:
    health = _read_json(OUT / "system_health.json")
    for chk in health.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == "target_portfolio_guard":
            detail = chk.get("detail") or {}
            status = str(chk.get("status") or detail.get("severity") or "unknown").lower()
            return status, detail
    return "unknown", {}


def _target_write_count(run_id: str | None = None) -> int:
    n = 0
    audit_path = OUT / "target_write_audit.jsonl"
    if not audit_path.exists():
        return 0
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if run_id and ev.get("run_id") != run_id:
            continue
        if ev.get("target_write_allowed") is True:
            n += 1
    return n


def _actual_buy_allowed() -> int:
    from src.report.execution_metrics import count_executable_actions

    final = _read_json(OUT / "final_execution_decision.json")
    return int(count_executable_actions(final).get("actual_buy_allowed_count") or 0)


def _policy_cap_unchanged(baseline: dict[str, Any]) -> bool:
    acc = _read_json(OUT / "acceptance_report.json")
    cur_cap = acc.get("policy_cap") or acc.get("policy_cap_result") or {}
    base_cap = baseline.get("policy_cap") or baseline.get("policy_cap_result") or {}
    if not base_cap and not cur_cap:
        return True
    return json.dumps(cur_cap, sort_keys=True) == json.dumps(base_cap, sort_keys=True)


def _gate_thresholds_unchanged(baseline: dict[str, Any]) -> bool:
    acc = _read_json(OUT / "acceptance_report.json")
    for key in ("data_gate", "portfolio_gate", "alpha_gate", "health_gate"):
        if baseline.get(key) and acc.get(key) and baseline.get(key) != acc.get(key):
            return False
    return True


def _approval_bridge_connected() -> bool:
    audit_path = OUT / "target_write_audit.jsonl"
    if not audit_path.exists():
        return False
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("target_write_source") == "approval_bridge" and ev.get("target_write_allowed") is True:
            return True
    return False


def _snapshot_file_mtimes(paths: list[Path]) -> dict[str, float]:
    return {str(p): p.stat().st_mtime if p.exists() else 0.0 for p in paths}


def _collect_metrics(prof: dict[str, Any], diag: dict[str, Any]) -> dict[str, Any]:
    tg_status, _ = _target_guard_status()
    slowest = prof.get("slowest_steps") or []
    slowest_step = slowest[0]["step"] if slowest else "—"
    return {
        "total_seconds": prof.get("total_seconds"),
        "slowest_step": slowest_step,
        "target_guard": tg_status,
        "target_write_count": _target_write_count(str(prof.get("run_id") or "")),
        "actual_buy_allowed": _actual_buy_allowed(),
        "no_action_expected": diag.get("no_action_is_expected"),
        "status_alignment_pass": diag.get("status_alignment_pass"),
        "pykrx_call_count": prof.get("pykrx_call_count"),
        "cache_hit_count": prof.get("cache_hit_count"),
        "cache_miss_count": prof.get("cache_miss_count"),
        "bundle_size_mb": prof.get("bundle_size_mb"),
        "generated_files_count": prof.get("generated_files_count"),
        "entrypoint": prof.get("entrypoint"),
        "step_timings": prof.get("step_timings") or {},
        "notes": prof.get("notes") or [],
    }


def _validate_common(mode: str, metrics: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if metrics.get("entrypoint") != "cli":
        errs.append(f"entrypoint={metrics.get('entrypoint')} (expected cli)")
    tg = str(metrics.get("target_guard") or "")
    if tg not in {"pass", "ok"}:
        errs.append(f"target_guard={tg} (expected pass)")
    if int(metrics.get("target_write_count") or 0) != 0:
        errs.append(f"target_write_count={metrics.get('target_write_count')}")
    if _approval_bridge_connected():
        errs.append("approval_bridge connected with allowed write")
    if not _policy_cap_unchanged(baseline):
        errs.append("policy_cap changed")
    if not _gate_thresholds_unchanged(baseline):
        errs.append("gate threshold changed")
    if not (OUT / "no_action_diagnostics.json").exists():
        errs.append("no_action_diagnostics.json missing")
    elif metrics.get("status_alignment_pass") is not True:
        errs.append(f"status_alignment_pass={metrics.get('status_alignment_pass')}")
    if not (OUT / "runtime_profile.json").exists():
        errs.append("runtime_profile.json missing")
    prof = _read_json(OUT / "runtime_profile.json")
    if prof.get("run_mode") != mode:
        errs.append(f"runtime_profile.run_mode={prof.get('run_mode')}")
    return errs


def _validate_mode(mode: str, metrics: dict[str, Any], *, before_mtimes: dict[str, float] | None = None) -> list[str]:
    errs: list[str] = []
    steps = metrics.get("step_timings") or {}
    notes = " ".join(metrics.get("notes") or [])

    if mode == "quick":
        if int(metrics.get("pykrx_call_count") or 0) != 0:
            errs.append(f"quick pykrx_call_count={metrics.get('pykrx_call_count')}")
        if "data_refresh" in steps and steps["data_refresh"] > 0.01:
            errs.append("quick ran data_refresh")
        if "data_hooks" in steps and steps["data_hooks"] > 0.01:
            errs.append("quick ran data_hooks")
        if "pipeline_core" in steps:
            errs.append("quick ran pipeline_core")
        if not (OUT / "daily_report.md").exists():
            errs.append("daily_report.md missing")

    elif mode == "standard":
        if not (OUT / "alpha_v2_summary.json").exists() and not (OUT / "alpha_scored_universe.csv").exists():
            errs.append("alpha outputs missing after standard")
        if not (OUT / "data_gate_diagnostics.json").exists():
            errs.append("data_gate_diagnostics missing")
        if not metrics.get("slowest_step") or metrics.get("slowest_step") == "—":
            errs.append("slowest_steps empty")

    elif mode == "deep":
        if int(metrics.get("pykrx_call_count") or 0) == 0 and int(metrics.get("cache_miss_count") or 0) == 0:
            errs.append("deep: no pykrx/cache activity recorded (check flow refresh)")
        zip_path = OUT / "ai_export_bundle.zip"
        if not zip_path.exists() and float(metrics.get("bundle_size_mb") or 0) <= 0:
            errs.append("deep: zip bundle not created")
        if "kosdaq_universe_sync" not in steps and "data_hooks" not in steps:
            errs.append("deep: kosdaq/data_hooks step not in profile")

    elif mode == "bundle_only":
        if "pipeline_core" in steps:
            errs.append("bundle_only ran pipeline_core")
        if before_mtimes:
            for path, mtime in before_mtimes.items():
                p = Path(path)
                if p.exists() and p.stat().st_mtime != mtime:
                    name = p.name
                    if name in {"alpha_v2_scored.csv", "alpha_scored_universe.csv", "investor_flows.csv"}:
                        errs.append(f"bundle_only modified {name}")
        if float(metrics.get("bundle_size_mb") or 0) <= 0 and not (OUT / "ai_export_bundle.zip").exists():
            errs.append("bundle_only: no bundle/zip output")

    if mode != "bundle_only" and "cache-only" not in notes.lower() and mode == "quick":
        if "Actual Buy Allowed validated" not in notes:
            pass  # advisory note optional

    return errs


def _run_cli(mode: str, timeout_sec: int) -> tuple[int, float]:
    cmd = [PYTHON, "-m", "src.main", "--run-mode", mode, "--no-backtest"]
    t0 = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        env=env,
    )
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        print(proc.stdout[-2000:] if proc.stdout else "")
        print(proc.stderr[-2000:] if proc.stderr else "", file=sys.stderr)
    return proc.returncode, elapsed


def verify_all() -> list[ModeResult]:
    baseline_acc = _read_json(OUT / "acceptance_report.json")
    baseline = {"policy_cap": baseline_acc.get("policy_cap"), "data_gate": baseline_acc.get("data_gate")}

    modes: list[tuple[str, int]] = [
        ("quick", 120),
        ("standard", 900),
        ("deep", 1800),
        ("bundle_only", 120),
    ]
    results: list[ModeResult] = []

    for mode, timeout in modes:
        mr = ModeResult(run_mode=mode)
        before_mtimes = None
        if mode == "bundle_only":
            before_mtimes = _snapshot_file_mtimes([
                OUT / "alpha_v2_scored.csv",
                OUT / "alpha_scored_universe.csv",
                DATA / "investor_flows.csv",
            ])

        print(f"\n=== Running: --run-mode {mode} (timeout {timeout}s) ===")
        try:
            code, elapsed = _run_cli(mode, timeout)
            mr.exit_code = code
            mr.elapsed_sec = round(elapsed, 2)
        except subprocess.TimeoutExpired:
            mr.errors.append(f"timeout after {timeout}s")
            results.append(mr)
            continue
        except Exception as exc:
            mr.errors.append(str(exc))
            results.append(mr)
            continue

        prof = _read_json(OUT / "runtime_profile.json")
        diag = _read_json(OUT / "no_action_diagnostics.json")
        mr.metrics = _collect_metrics(prof, diag)

        if code != 0:
            mr.errors.append(f"exit_code={code}")

        mr.errors.extend(_validate_common(mode, mr.metrics, baseline))
        mr.errors.extend(_validate_mode(mode, mr.metrics, before_mtimes=before_mtimes))
        mr.passed = code == 0 and not mr.errors
        results.append(mr)

        status = "PASS" if mr.passed else "FAIL"
        print(f"[{status}] {mode} exit={code} elapsed={mr.elapsed_sec}s errors={mr.errors}")

    return results


def _print_summary_table(results: list[ModeResult]) -> None:
    cols = [
        "run_mode", "exit_code", "total_seconds", "slowest_step", "target_guard",
        "target_write_count", "actual_buy_allowed", "no_action_expected",
        "pykrx_call_count", "cache_hit_count", "cache_miss_count",
        "bundle_size_mb", "generated_files_count", "verdict",
    ]
    print("\n=== CLI 4-MODE CLEAN RUN SUMMARY ===")
    header = " | ".join(cols)
    print(header)
    print("-" * len(header))
    for r in results:
        m = r.metrics
        row = [
            r.run_mode,
            str(r.exit_code),
            str(m.get("total_seconds", r.elapsed_sec)),
            str(m.get("slowest_step", "—")),
            str(m.get("target_guard", "—")),
            str(m.get("target_write_count", "—")),
            str(m.get("actual_buy_allowed", "—")),
            str(m.get("no_action_expected", "—")),
            str(m.get("pykrx_call_count", "—")),
            str(m.get("cache_hit_count", "—")),
            str(m.get("cache_miss_count", "—")),
            str(m.get("bundle_size_mb", "—")),
            str(m.get("generated_files_count", "—")),
            "PASS" if r.passed else "FAIL",
        ]
        print(" | ".join(row))

    all_pass = all(r.passed for r in results)
    print("\nOVERALL:", "PASS" if all_pass else "FAIL")
    if not all_pass:
        for r in results:
            if r.errors:
                print(f"  {r.run_mode}: {r.errors}")


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import argparse as _ap

    parser = _ap.ArgumentParser(description="CLI 4-mode clean run verification")
    parser.add_argument("--verify-only", action="store_true", help="Validate last run outputs without re-executing")
    parser.add_argument("--modes", nargs="*", default=None, help="Subset of modes to run/verify")
    args = parser.parse_args()

    if args.verify_only:
        modes = args.modes or ["quick", "standard", "deep", "bundle_only"]
        baseline_acc = _read_json(OUT / "acceptance_report.json")
        baseline = {"policy_cap": baseline_acc.get("policy_cap"), "data_gate": baseline_acc.get("data_gate")}
        results: list[ModeResult] = []
        prof = _read_json(OUT / "runtime_profile.json")
        current_mode = str(prof.get("run_mode") or "")
        for mode in modes:
            mr = ModeResult(run_mode=mode, exit_code=0 if mode == current_mode else -1)
            if mode != current_mode:
                mr.errors.append(f"runtime_profile shows {current_mode}, not {mode} (re-run mode separately)")
                results.append(mr)
                continue
            diag = _read_json(OUT / "no_action_diagnostics.json")
            mr.metrics = _collect_metrics(prof, diag)
            mr.errors.extend(_validate_common(mode, mr.metrics, baseline))
            mr.errors.extend(_validate_mode(mode, mr.metrics))
            mr.passed = not mr.errors
            results.append(mr)
        _print_summary_table(results)
        return 0 if all(r.passed for r in results if r.exit_code == 0) else 1

    results = verify_all()
    _print_summary_table(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
