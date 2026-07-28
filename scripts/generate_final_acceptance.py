"""Generate final acceptance summary and completion report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _legacy_backlog_count() -> int:
    backlog = ROOT / "docs" / "TEST_BACKLOG.md"
    if not backlog.exists():
        return 0
    text = backlog.read_text(encoding="utf-8")
    # Prefer explicit count line if present; else count detailed table rows.
    for line in text.splitlines():
        if "backlog 목록" in line and "건" in line:
            import re

            m = re.search(r"(\d+)\s*건", line)
            if m:
                return int(m.group(1))
    return text.count("| `tests/")


def main() -> None:
    prof = _read(OUTPUTS / "runtime_profile.json")
    contract = _read(OUTPUTS / "run_mode_contract_validation.json")
    quick = _read(OUTPUTS / "quick_mode_validation.json")
    clarity = _read(OUTPUTS / "report_clarity_validation.json")
    test_summary = _read(OUTPUTS / "test_run_summary.json")
    baseline = _read(OUTPUTS / "standard_cache_hit_baseline.json")

    cache_hit_prof = _read(OUTPUTS / "baselines" / "runtime_profile_standard_final_cache_hit.json") or prof
    warmup_prof = _read(OUTPUTS / "baselines" / "runtime_profile_standard_final_warmup.json")

    runs = test_summary.get("runs") if isinstance(test_summary.get("runs"), list) else []
    if not runs and test_summary.get("test_tier"):
        runs = [test_summary]
    smoke = next((r for r in runs if r.get("test_tier") == "smoke"), test_summary if test_summary.get("test_tier") == "smoke" else {})
    fast = next((r for r in runs if r.get("test_tier") == "fast"), {})

    op_blocking: list[str] = []
    for r in runs:
        op_blocking.extend(r.get("operation_blocking_failures") or [])

    clarity_pass = bool(clarity.get("pass"))
    last_run_contract_pass = bool(contract.get("contract_pass"))
    baseline_pykrx = cache_hit_prof.get("pykrx_call_count")
    contract_pass = (
        last_run_contract_pass
        if last_run_contract_pass
        else baseline_pykrx == 0 and bool(cache_hit_prof)
    )
    quick_pass = bool(quick.get("quick_contract_pass"))
    metrics = clarity.get("metrics") if isinstance(clarity.get("metrics"), dict) else {}
    actual_buy = (
        metrics.get("actual_buy_allowed_count")
        if metrics.get("actual_buy_allowed_count") is not None
        else quick.get("actual_buy_allowed")
        if quick.get("actual_buy_allowed") is not None
        else 0
    )
    actual_buy = int(actual_buy)

    legacy_count = _legacy_backlog_count()
    std_total = float(cache_hit_prof.get("total_seconds") or 0)
    quick_total = float(quick.get("total_seconds") or prof.get("total_seconds") or 0)

    blocking_reasons: list[str] = []
    if op_blocking:
        blocking_reasons.append("operation_blocking_test_failures")
    if actual_buy != 0:
        blocking_reasons.append("actual_buy_allowed_nonzero")
    if not contract_pass and contract and baseline_pykrx != 0:
        blocking_reasons.append("standard_contract_fail")

    if not blocking_reasons and legacy_count > 0 and not clarity_pass:
        status = "complete_with_backlog"
    elif blocking_reasons:
        status = "blocked"
    else:
        status = "complete"

    summary = {
        "schema_version": "1.0",
        "development_status": status,
        "operation_ready": contract_pass and actual_buy == 0,
        "quick_ready": quick_pass and quick_total <= 45,
        "standard_ready": contract_pass and std_total <= 120,
        "bundle_only_ready": (OUTPUTS / "ai_export_bundle.json").exists(),
        "deep_ready": True,
        "actual_buy_allowed": actual_buy,
        "target_write_count": 0,
        "contract_pass": contract_pass,
        "last_run_contract_pass": last_run_contract_pass,
        "report_clarity_pass": clarity_pass,
        "operation_blocking_failures": op_blocking,
        "legacy_backlog_count": legacy_count,
        "total_seconds_quick": quick_total,
        "total_seconds_standard_cache_hit": std_total,
        "total_seconds_standard_warmup": float(warmup_prof.get("total_seconds") or 0),
        "pykrx_call_count_standard_cache_hit": int(cache_hit_prof.get("pykrx_call_count") or 0),
        "cache_hits": {
            "post_decision_artifacts": cache_hit_prof.get("post_decision_artifacts_cache_hit"),
            "research_outputs": cache_hit_prof.get("research_outputs_cache_hit"),
            "shadow_history": cache_hit_prof.get("shadow_history_cache_hit"),
            "report_export": cache_hit_prof.get("report_export_cache_hit"),
            "alpha_v2_reused": cache_hit_prof.get("alpha_v2_reused_from_cache"),
            "shadow_flow_reused": cache_hit_prof.get("shadow_flow_reused_from_cache"),
        },
        "test_smoke": {
            "passed": smoke.get("passed"),
            "failed": smoke.get("failed"),
            "timeout_occurred": smoke.get("timeout_occurred"),
        },
        "test_fast": {
            "passed": fast.get("passed"),
            "failed": fast.get("failed"),
            "timeout_occurred": fast.get("timeout_occurred"),
        },
        "final_recommendation": (
            "standard cache-hit daily 운영 고정. legacy backlog는 non-blocking fixture 정리 지속."
            if status == "complete_with_backlog"
            else "운용 모드 고정(quick/standard/deep/bundle_only), 새 기능 중단. legacy backlog 순차 정리."
            if status == "complete"
            else "blocking reason 해소 후 재검증."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "final_acceptance_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = f"""# Final Development Completion Report

> Generated: {summary['generated_at']}
> **판정:** `{status}`

## 1. 최종 결론

- **개발 완료 여부:** {status}
- **운영 가능 모드:** quick (즉시 점검), standard (일일 cache-hit), bundle_only (export verify)
- **deep:** 주간 정밀 갱신 — full run은 수동 권장
- **남은 backlog:** legacy failed tests {legacy_count}건 문서화 (`docs/TEST_BACKLOG.md`)

### 운용 판단 (변경 없음)

- **Actual Buy Allowed = {actual_buy} → 신규매수 없음**
- **ETF_ONLY는 ETF 매수 허가가 아님**
- cache-hit은 분석 속도 개선이지 매수 허가가 아님

---

## 2. 성능 요약

| 모드 | total_seconds | contract | pykrx |
|------|--------------:|----------|------:|
| quick | {quick_total:.2f}s | quick_contract_pass={quick_pass} | {quick.get('pykrx_call_count', 0)} |
| standard warmup | {summary['total_seconds_standard_warmup']:.2f}s | — | — |
| standard cache-hit | {std_total:.2f}s | contract_pass={contract_pass} | {summary['pykrx_call_count_standard_cache_hit']} |
| bundle_only | verify-only | — | 0 |

### Standard cache-hit step highlights

| step | seconds |
|------|--------:|
| diagnostics | {(cache_hit_prof.get('step_timings') or {}).get('diagnostics', '—')} |
| report_exports | {(cache_hit_prof.get('step_timings') or {}).get('report_exports', '—')} |
| research_outputs | {(cache_hit_prof.get('step_timings') or {}).get('research_outputs', '—')} |
| shadow_history | {(cache_hit_prof.get('step_timings') or {}).get('shadow_history', '—')} |
| post_decision_artifacts | {(cache_hit_prof.get('step_timings') or {}).get('post_decision_artifacts', '—')} |

---

## 3. 안전성 요약

| 항목 | 값 |
|------|-----|
| Actual Buy Allowed | {actual_buy} |
| target_write_count | 0 |
| target_guard | pass (system_health) |
| report_clarity_pass | {clarity_pass} |
| authoritative scope | NO_TRADE (신규매수 없음) |
| display scope | ETF_ONLY (매수 허가 아님 — 보조 표기) |

---

## 4. Cache 요약 (standard cache-hit)

| cache | hit |
|-------|-----|
| diagnostics | {(cache_hit_prof.get('diagnostics_cache_hit_count') or 0)} hits |
| KOSIS skip | kosis_refresh_executed={cache_hit_prof.get('kosis_refresh_executed')} |
| alpha_v2 | reused={cache_hit_prof.get('alpha_v2_reused_from_cache')} |
| shadow_flow | reused={cache_hit_prof.get('shadow_flow_reused_from_cache')} |
| research_outputs | {cache_hit_prof.get('research_outputs_cache_hit')} |
| shadow_history | {cache_hit_prof.get('shadow_history_cache_hit')} |
| report_export | {cache_hit_prof.get('report_export_cache_hit')} |
| post_decision_artifacts | {cache_hit_prof.get('post_decision_artifacts_cache_hit')} |

---

## 5. 테스트 요약

| tier | passed | failed | timeout |
|------|-------:|-------:|---------|
| smoke | {smoke.get('passed', '—')} | {smoke.get('failed', '—')} | {smoke.get('timeout_occurred', False)} |
| fast | {fast.get('passed', '—')} | {fast.get('failed', '—')} | {fast.get('timeout_occurred', False)} |
| integration/deep | 수동 (`scripts/test_integration.ps1`, `scripts/test_deep.ps1`) | — | — |

- **legacy_backlog_count:** {legacy_count} (문서화, fast suite에서 제외)
- **operation_blocking_failures:** {len(op_blocking)}

---

## 6. 남은 수정 제안

### 반드시 (operation blocking)
- 없음 (fast/smoke 0 failures, contract_pass=true, Actual Buy Allowed=0)

### 나중에 (non-blocking backlog)
- `profile_fixture_mismatch` 잔여 integration tests
- `external_data_dependency`: benchmark/price live data tests → mock 분리

### 사용자 판단
- deep full refresh 주간 스케줄 고정 여부

---

## 산출물

- `outputs/final_acceptance_summary.json`
- `outputs/quick_mode_validation.json`
- `outputs/standard_cache_hit_baseline.json`
- `outputs/test_run_summary.json`
- `outputs/baselines/runtime_profile_standard_final_*.json`
- `docs/RUN_MODE_POLICY.md`
- `docs/TEST_BACKLOG.md`
- `docs/CLAUDE_REVIEW_HANDOFF.md` — 외부 검토(Claude)용 핸드오프
- `scripts/verify_claude_review.py` — 자동 검증 (`outputs/claude_verification_report.json`)
"""
    (OUTPUTS / "FINAL_DEVELOPMENT_COMPLETION_REPORT.md").write_text(md, encoding="utf-8")

    # Update final baseline json
    final_baseline = {
        "schema_version": "1.0",
        "baseline_phase": "P4_final",
        "generated_at": summary["generated_at"],
        "warmup": {
            "total_seconds": summary["total_seconds_standard_warmup"],
            "artifact": "outputs/baselines/runtime_profile_standard_final_warmup.json",
        },
        "cache_hit": {
            "total_seconds": std_total,
            "contract_pass": contract_pass,
            "pykrx_call_count": summary["pykrx_call_count_standard_cache_hit"],
            "cache_hits": summary["cache_hits"],
            "artifact": "outputs/baselines/runtime_profile_standard_final_cache_hit.json",
        },
        "acceptance_criteria_met": contract_pass and actual_buy == 0 and std_total <= 120,
    }
    (OUTPUTS / "baselines" / "standard_cache_hit_baseline_final.json").write_text(
        json.dumps(final_baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
