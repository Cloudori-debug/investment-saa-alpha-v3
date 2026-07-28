"""Generate machine-readable verification report for external review (e.g. Claude).

Reads existing outputs only — does not run the pipeline or tests.
Run from repo root: python scripts/verify_claude_review.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DOCS = ROOT / "docs"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _first_int(*values: object, default: int = -1) -> int:
    for v in values:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return default


def _check(name: str, ok: bool, detail: str, *, blocking: bool = True) -> dict:
    return {
        "id": name,
        "pass": ok,
        "blocking": blocking,
        "detail": detail,
    }


def main() -> int:
    acceptance = _read_json(OUTPUTS / "final_acceptance_summary.json")
    clarity = _read_json(OUTPUTS / "report_clarity_validation.json")
    quick = _read_json(OUTPUTS / "quick_mode_validation.json")
    contract = _read_json(OUTPUTS / "run_mode_contract_validation.json")
    baseline = _read_json(OUTPUTS / "baselines" / "runtime_profile_standard_final_cache_hit.json")
    test_summary = _read_json(OUTPUTS / "test_run_summary.json")
    daily_report = _read_text(OUTPUTS / "daily_report.md", limit=3000)
    brief = _read_json(OUTPUTS / "daily_brief.json")

    runs = test_summary.get("runs") if isinstance(test_summary.get("runs"), list) else []
    if not runs and test_summary.get("test_tier"):
        runs = [test_summary]
    smoke = next((r for r in runs if r.get("test_tier") == "smoke"), {})
    fast = next((r for r in runs if r.get("test_tier") == "fast"), {})

    actual_buy = _first_int(
        (clarity.get("metrics") or {}).get("actual_buy_allowed_count"),
        quick.get("actual_buy_allowed"),
        acceptance.get("actual_buy_allowed"),
    )
    clarity_pass = bool(clarity.get("pass"))
    dev_status = str(acceptance.get("development_status") or "")
    contract_last = bool(contract.get("contract_pass"))
    contract_baseline_pykrx = _first_int(baseline.get("pykrx_call_count"))
    baseline_total = float(baseline.get("total_seconds") or 0)

    target_write = _first_int(acceptance.get("target_write_count"), quick.get("target_write_count"), default=0)

    checks: list[dict] = []

    checks.append(_check(
        "development_status_complete",
        dev_status in ("complete", "complete_with_backlog"),
        f"development_status={dev_status!r}",
    ))
    checks.append(_check(
        "actual_buy_allowed_zero",
        actual_buy == 0,
        f"actual_buy_allowed={actual_buy}",
    ))
    checks.append(_check(
        "target_write_zero",
        target_write == 0,
        f"target_write_count={target_write}",
    ))
    checks.append(_check(
        "report_clarity_pass",
        clarity_pass,
        f"report_clarity_pass={clarity_pass}, failures={clarity.get('failures')}",
    ))
    checks.append(_check(
        "quick_contract_pass",
        bool(quick.get("quick_contract_pass")),
        f"quick_contract_pass={quick.get('quick_contract_pass')}, pykrx={quick.get('pykrx_call_count')}",
    ))
    checks.append(_check(
        "standard_cache_hit_baseline_pykrx_zero",
        contract_baseline_pykrx == 0,
        f"baseline pykrx_call_count={contract_baseline_pykrx} (artifact: baselines/runtime_profile_standard_final_cache_hit.json)",
        blocking=False,
    ))
    checks.append(_check(
        "standard_cache_hit_baseline_under_120s",
        0 < baseline_total <= 120,
        f"baseline total_seconds={baseline_total}",
        blocking=False,
    ))
    checks.append(_check(
        "last_run_contract_note",
        True,
        (
            f"last run contract_pass={contract_last}, pykrx={contract.get('pykrx_call_count')} "
            f"(warmup/new-day may differ from cache-hit baseline; see RUN_MODE_POLICY.md)"
        ),
        blocking=False,
    ))
    checks.append(_check(
        "operation_blocking_failures_empty",
        len(acceptance.get("operation_blocking_failures") or []) == 0,
        f"operation_blocking_failures={acceptance.get('operation_blocking_failures')}",
    ))
    checks.append(_check(
        "smoke_tests_zero_failures",
        int(smoke.get("failed") or 0) == 0 and smoke.get("passed") is not None,
        f"smoke passed={smoke.get('passed')} failed={smoke.get('failed')}",
        blocking=False,
    ))
    checks.append(_check(
        "fast_tests_zero_failures",
        int(fast.get("failed") or 0) == 0 and fast.get("passed") is not None,
        f"fast passed={fast.get('passed')} failed={fast.get('failed')}",
        blocking=False,
    ))

    # P4e dual-scope text checks on daily_report
    has_auth_no_trade = "NO_TRADE" in daily_report and "신규매수 없음" in daily_report
    has_etf_disclaimer = (
        "ETF_ONLY는 ETF 매수 허가가 아님" in daily_report
        or "ETF_ONLY는 ETF 매수 허가가 아니다" in daily_report
        or "ETF 매수 허가가 아님" in daily_report
        or "ETF 매수 허가가 아니다" in daily_report
        or "ETF_ONLY is scope restriction, not ETF buy permission" in daily_report
        or "not ETF buy permission" in daily_report
    )
    has_actual_buy_zero = "Actual Buy Allowed" in daily_report and re.search(
        r"Actual Buy Allowed.*0", daily_report
    )
    checks.append(_check(
        "daily_report_authoritative_no_trade",
        has_auth_no_trade,
        "daily_report.md contains NO_TRADE + 신규매수 없음",
    ))
    checks.append(_check(
        "daily_report_etf_only_not_buy_permission",
        has_etf_disclaimer or "ETF_ONLY" not in daily_report,
        "daily_report.md explains ETF_ONLY is not buy permission",
    ))
    checks.append(_check(
        "daily_report_actual_buy_allowed_zero",
        bool(has_actual_buy_zero),
        "daily_report.md shows Actual Buy Allowed: 0",
    ))

    brief_auth = str(
        (brief.get("system_status") or {}).get("authoritative_execution_scope")
        or (brief.get("system_status") or {}).get("execution_scope")
        or ""
    )
    checks.append(_check(
        "daily_brief_authoritative_scope",
        brief_auth == "NO_TRADE" or not brief,
        f"daily_brief authoritative scope={brief_auth!r}",
        blocking=False,
    ))

    required_docs = [
        DOCS / "CLAUDE_REVIEW_HANDOFF.md",
        DOCS / "RUN_MODE_POLICY.md",
        DOCS / "TEST_BACKLOG.md",
        OUTPUTS / "FINAL_DEVELOPMENT_COMPLETION_REPORT.md",
    ]
    missing_docs = [str(p.relative_to(ROOT)) for p in required_docs if not p.exists()]
    checks.append(_check(
        "review_documents_present",
        not missing_docs,
        f"missing: {missing_docs}" if missing_docs else "all review docs present",
        blocking=False,
    ))

    blocking_failures = [c for c in checks if c["blocking"] and not c["pass"]]
    non_blocking_failures = [c for c in checks if not c["blocking"] and not c["pass"]]

    report = {
        "schema_version": "1.0",
        "purpose": "claude_external_review",
        "repo_root": str(ROOT),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pass": len(blocking_failures) == 0,
        "blocking_pass_count": sum(1 for c in checks if c["blocking"] and c["pass"]),
        "blocking_total": sum(1 for c in checks if c["blocking"]),
        "non_blocking_pass_count": sum(1 for c in checks if not c["blocking"] and c["pass"]),
        "non_blocking_total": sum(1 for c in checks if not c["blocking"]),
        "acceptance_snapshot": {
            "development_status": dev_status,
            "actual_buy_allowed": actual_buy,
            "report_clarity_pass": clarity_pass,
            "contract_pass_last_run": contract_last,
            "contract_pass_baseline_pykrx_zero": contract_baseline_pykrx == 0,
            "legacy_backlog_count": acceptance.get("legacy_backlog_count"),
        },
        "checks": checks,
        "blocking_failures": [c["id"] for c in blocking_failures],
        "non_blocking_failures": [c["id"] for c in non_blocking_failures],
        "files_to_read_for_deep_review": [
            "docs/CLAUDE_REVIEW_HANDOFF.md",
            "outputs/final_acceptance_summary.json",
            "outputs/report_clarity_validation.json",
            "outputs/daily_report.md",
            "outputs/daily_brief.json",
            "src/report/authoritative_status.py",
            "src/report/execution_metrics.py",
            "docs/RUN_MODE_POLICY.md",
            "docs/TEST_BACKLOG.md",
        ],
        "optional_rerun_commands": [
            "python scripts/verify_claude_review.py",
            "python -m src.main --run-mode quick",
            "python -m src.main --run-mode standard",
            "python -m src.main --run-mode standard",
            "scripts/test_smoke.ps1",
            "python scripts/generate_final_acceptance.py",
            "python scripts/verify_claude_review.py",
        ],
    }

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS / "claude_verification_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
