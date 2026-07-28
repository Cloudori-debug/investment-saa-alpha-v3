# 레짐 오버라이드 격차 경고 — 결과

> 명세: `docs/REGIME_OVERRIDE_DIVERGENCE_ALERT_SPEC.md`  
> 범위: **가시성/경고만** — 오버라이드 자동 해제·레짐 산출 로직·policy_cap/scope 미변경

## 1. 구현

| 항목 | 내용 |
|------|------|
| 공통 | `src/validation/regime_override_divergence.py` — `regime_severity`, `regime_override_gap`, `assess_regime_override_divergence` |
| 서수 | RISK_ON(0) < YELLOW_STABLE(1) < CAUTION(2) < RISK_OFF(3) < CRISIS(4) |
| 임계 | `data/compass_rules.yaml` → `regime_rules.override_divergence_warn_gap: 2` |
| AC-05b | `acceptance_check._check_regime_override_divergence` — 시간 기반 AC-05와 분리 |
| health | `system_health` `regime_computed` — gap≥2면 `warn` (값 부재 시만 `fail`) |

경고는 **양수 gap**(산출이 적용보다 심각 = 완화 오버라이드) + `override_active` + `gap >= threshold`일 때만.  
문구에 gap·computed·applied·근거·설정일 + “자동 해제 없음 / 재확인 보조” 명시.

## 2. 테스트

`tests/test_regime_override_divergence.py` — **7 passed**

- CRISIS→YELLOW_STABLE gap=3 → **warn**
- CAUTION→YELLOW_STABLE gap=1 → **pass**(정보)
- 동일 레짐 gap=0 → **pass**
- AC-05 영업일 경과 warn **회귀 없음**

## 3. 라이브

`outputs/compass_regime.json`이 있으면 AC-05b / health `regime_computed`가 동일 격차로 warn.  
(파이프라인 재실행 시 acceptance·health에 자동 포함.)

## 4. 금지 준수

- 오버라이드 값/만료 **미변경**
- `regime_engine._classify_risk_regime` / `_manual_regime_effective` **미변경**
- policy_cap / execution_scope / throttle / guards **미변경**
