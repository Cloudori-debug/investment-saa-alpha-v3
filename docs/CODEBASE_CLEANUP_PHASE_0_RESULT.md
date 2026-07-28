# Cleanup Phase 0 — `alpha_v0_2` archive

> SPEC: [`CODEBASE_CLEANUP_PHASE_0_1_2_SPEC.md`](CODEBASE_CLEANUP_PHASE_0_1_2_SPEC.md)  
> 원칙: **삭제 아님 · git mv만**. `src/alpha/` · 익절엔진 미변경. v2 경로는 `alpha_shadow_policy`에서 그대로 유지.

## 1. 이동 목록

| 원본 | archive |
|------|---------|
| `src/alpha_v0_2/` (12 files) | `archive/20260715_alpha_v0_2/` |
| `tests/test_alpha_v0_2_shadow.py` | `archive/20260715_tests/test_alpha_v0_2_shadow.py` |

파일: `__init__.py`, `catalyst_score.py`, `classifier.py`, `config_loader.py`, `exclusion_gate.py`, `momentum_score.py`, `pipeline.py`, `quality_score.py`, `risk_budget.py`, `schemas.py`, `universe.py`, `value_score.py` + shadow 테스트 1.

## 2. 잔여 참조 처리

[`src/alpha_shadow_policy.py`](../src/alpha_shadow_policy.py):
- 모듈 상단 `try: from src.alpha_v0_2.pipeline import … except ImportError: _run_alpha_v0_2_shadow = None`
- `v0_2_enabled`인데 모듈 없으면 `alpha_v0_2_shadow_skipped` / `reason=module_unavailable` 로그 후 스킵
- **v2 / flow 분기 그대로** (충돌 없음)
- 공개 함수 시그니처 유지

테스트 패치 경로: `src.alpha_shadow_policy._run_alpha_v0_2_shadow` (`tests/test_alpha_shadow_config.py`).

`test_alpha_v0_2.py`는 **signal board** 테스트명 — 패키지와 무관하므로 **이동하지 않음**.

## 3. 검증

| 항목 | 결과 |
|------|------|
| `import src.main` | ok |
| `_run_alpha_v0_2_shadow is None` | True (archived) |
| `v0_2_enabled=true` 시 skip 로그 | `reason=module_unavailable` |
| `pytest tests/test_alpha_shadow_config.py` | **10 passed** |
| 관련 묶음 (export_daily_brief + take_profit/gap/worksheet 등) | **31 passed** |
| `test_action_planner::test_kr_alpha_replace_theoretical_low_priority` | **사전 존재 fail** (Expected Low got High) — phase 0과 무관 |
| 전체 pytest | PowerShell 파이프 버퍼로 장시간 대기 — 핵심 경로·shadow 테스트로 갈음. 원하시면 별도 전체 재실행 |
| 커밋 | `0adf388 cleanup: archive alpha_v0_2 (phase 0)` |

**다음:** 원장 검증 후 1단계(`value_list`) 진행 여부 결정.
