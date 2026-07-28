"""P4c — tiered pytest runner with timeout and test_run_summary.json."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_SUMMARY = ROOT / "outputs" / "test_run_summary.json"

TIER_CONFIG: dict[str, dict[str, object]] = {
    "smoke": {
        "timeout_seconds": 300,
        "expr": "smoke",
        "ignore": [],
    },
    "fast": {
        "timeout_seconds": 1200,
        "expr": "fast and not integration and not slow and not network and not pykrx and not legacy_backlog",
        "ignore": [],
    },
    "integration": {
        "timeout_seconds": 3600,
        "expr": "integration and not deep",
        "ignore": [],
    },
    "deep": {
        "timeout_seconds": 7200,
        "expr": "slow or network or pykrx or external_data",
        "ignore": [],
    },
}

OPERATION_BLOCKING_PATTERNS: tuple[str, ...] = (
    "test_smoke_acceptance",
    "test_run_mode_contract",
    "test_run_mode_cli",
    "test_report_export_cache",
    "test_research_outputs_cache",
    "test_shadow_history_cache",
    "test_post_decision_artifacts",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_pytest_output(text: str) -> dict[str, int | bool]:
    passed = failed = skipped = errors = 0
    timeout_occurred = False
    m = re.search(r"(\d+) passed", text)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", text)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+) skipped", text)
    if m:
        skipped = int(m.group(1))
    m = re.search(r"(\d+) error", text)
    if m:
        errors = int(m.group(1))
    if "TimeoutExpired" in text or "timed out" in text.lower():
        timeout_occurred = True
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "timeout_occurred": timeout_occurred,
    }


def _failed_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("FAILED ")]


def _categorize_failures(failed: list[str]) -> dict[str, list[str]]:
    cats: dict[str, list[str]] = {
        "profile_fixture_mismatch": [],
        "alpha_policy_fixture_stale": [],
        "compass_expected_output_stale": [],
        "pipeline_cache_output_changed": [],
        "external_data_dependency": [],
        "true_regression": [],
        "unknown_needs_review": [],
    }
    for line in failed:
        low = line.lower()
        if "compass" in low or "defensive_balanced" in low or "core_absolute_return" in low or "ui_menus" in low:
            cats["profile_fixture_mismatch"].append(line)
        elif "alpha_screener" in low or "alpha_pipeline" in low or "action_planner" in low:
            cats["alpha_policy_fixture_stale"].append(line)
        elif "p0_alignment" in low or "report_consistency" in low or "portfolio_gap" in low:
            cats["pipeline_cache_output_changed"].append(line)
        elif "benchmark" in low or "tier_a_price" in low or "top10_sector" in low or "risk_limits" in low:
            cats["external_data_dependency"].append(line)
        elif any(p in line for p in OPERATION_BLOCKING_PATTERNS):
            cats["true_regression"].append(line)
        else:
            cats["unknown_needs_review"].append(line)
    return {k: v for k, v in cats.items() if v}


def run_tier(tier: str, *, append: bool = False) -> dict[str, object]:
    cfg = TIER_CONFIG[tier]
    t0 = time.perf_counter()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        str(cfg["expr"]),
        "-q",
        "--tb=no",
    ]
    for ign in cfg.get("ignore", []):
        cmd.extend(["--ignore", str(ign)])
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(cfg["timeout_seconds"]),
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        output = (exc.stdout or "") + "\n" + (exc.stderr or "") + "\nTimeoutExpired"
        exit_code = 124

    elapsed = round(time.perf_counter() - t0, 4)
    stats = _parse_pytest_output(output)
    stats["timeout_occurred"] = timed_out or bool(stats["timeout_occurred"])
    failed_lines = _failed_lines(output)
    failed_categories = _categorize_failures(failed_lines)
    operation_blocking = [
        ln for ln in failed_lines
        if any(p in ln for p in OPERATION_BLOCKING_PATTERNS)
    ]

    summary: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": datetime.now().astimezone().isoformat(timespec="seconds"),
        "test_tier": tier,
        "passed": stats["passed"],
        "failed": stats["failed"],
        "skipped": stats["skipped"],
        "errors": stats["errors"],
        "duration_seconds": elapsed,
        "timeout_seconds_limit": cfg["timeout_seconds"],
        "timeout_occurred": stats["timeout_occurred"],
        "exit_code": exit_code,
        "failed_tests": failed_lines[:50],
        "failed_categories": failed_categories,
        "operation_blocking_failures": operation_blocking,
        "generated_at": _utc_now(),
    }

    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    if append and OUTPUT_SUMMARY.exists():
        try:
            prev = json.loads(OUTPUT_SUMMARY.read_text(encoding="utf-8"))
            runs = prev.get("runs") if isinstance(prev.get("runs"), list) else []
            if "runs" not in prev:
                runs = [prev]
            runs.append(summary)
            doc = {"schema_version": "1.0", "runs": runs, "generated_at": _utc_now()}
        except Exception:
            doc = {"schema_version": "1.0", "runs": [summary], "generated_at": _utc_now()}
    else:
        doc = summary
    OUTPUT_SUMMARY.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output[-4000:] if len(output) > 4000 else output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pytest by tier")
    parser.add_argument("tier", choices=list(TIER_CONFIG.keys()))
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()
    summary = run_tier(args.tier, append=args.append)
    blocking = summary.get("operation_blocking_failures") or []
    if summary.get("timeout_occurred"):
        return 124
    if blocking:
        return 2
    return 0 if int(summary.get("failed") or 0) == 0 and int(summary.get("errors") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
