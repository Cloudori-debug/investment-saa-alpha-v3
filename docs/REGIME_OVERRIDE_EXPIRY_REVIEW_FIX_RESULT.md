# 수동 레짐 override 만료·재검토 — 구현 결과

> 명세: `docs/REGIME_OVERRIDE_EXPIRY_REVIEW_FIX_SPEC.md`

## 구현 요약

| ID | 내용 |
|----|------|
| **A** | `resolve_policy_cap(..., computed_regime=)` — **만료 시** 컴퓨티드 레짐으로 `cap_regime`/`max_execution_scope` 재계산 (`cap_source=computed_after_manual_expiry`). `final_decision_core`·`acceptance_check`에서 `compass_regime.json` computed 전달. |
| **B** | `assess_early_regime_review*` + **AC-05c** — 설정일 대비 낙폭 Δ≤`-5%p` → warn; 낙폭이 crisis 임계(`-15%`) 상회 → info(pass+detail). **자동 완화/해제 없음**. |
| **C** | AC-05 — `override_age_warn_days=5` warn / `override_age_escalation_days=15` → 메시지 「장기 미검토 — 재검토 시급」(여전히 warn, fail 아님). |

설정 (`compass_rules.yaml` `regime_rules`):
- `override_age_warn_days: 5`
- `override_age_escalation_days: 15`
- `early_review_worsening_dd_delta_pct: -5.0`
- `early_review_recovery_dd_threshold: -15.0`

## 검증

단위 테스트: `tests/test_policy_cap.py` + `tests/test_regime_override_expiry_review.py` + divergence 회귀 → **24 passed** (관련 suite).

| 명세 검증 | 결과 |
|-----------|------|
| A: 만료+computed=CRISIS → NO_TRADE | ✓ |
| A: 만료·computed 미전달(하위호환) → 기존 YELLOW/ETF_ONLY | ✓ |
| A: 미만료+computed=CRISIS → 여전히 YELLOW/ETF_ONLY | ✓ |
| B: 악화 Δ≤-5%p → warn | ✓ |
| B: 회복 → info, cap 값 불변 | ✓ |
| C: 6일 vs 16영업일 메시지 승격 | ✓ |

## 라이브 회귀 (as_of≈2026-07-13)

| 항목 | 결과 |
|------|------|
| execution scope | **ETF_ONLY 유지** (`expired=False`, source=`manual_regime`) — 오늘 판정 **불변** |
| AC-05 | warn · age=**13**영업일 (15 미만 → 장기 승격 전) |
| AC-05b | warn · gap=3 (기존과 동일) |
| AC-05c | **신규 warn** · worsening (−10.0% → −25.3%, Δ−15.3%p) — **알림만**, 캡/scope 변경 없음 |

## 불변

- override 자동 해제·자동 완화·만료 연장 없음
- `_manual_regime_effective` 폴백 유지 — policy_cap만 정합
- 캡 폭 테이블·execution_scope/throttle/guards 임계 **미변경**
- AC-05/05b/05c 모두 **fail 승격 없음** (실행 자동 차단 없음)
