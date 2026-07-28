# 수동 레짐 override 만료·재검토 메커니즘 — 개선 승인 명세서

> 근거: Claude 독립 분석 (이 문서가 조사 결과 겸 수정 명세 — 별도 INVESTIGATION 문서 없음)
> 배경: "정책캡이 너무 세다"는 문제 제기를 3가지 각도(캡의 폭 / 만료일 설계 / 레짐 분류 신뢰성)로 분해해 검토.
> 결론: 캡의 폭(ETF_ONLY, kr_alpha 차단) 자체는 4단계 캡 중 가장 관대한 축이라 변경 대상 아님.
> 레짐 분류 신뢰성(컴퓨티드 CRISIS vs 수동 YELLOW_STABLE)은 데이터로 확정 불가 — AC-05b가 이미 담당, 이번 범위 아님.
> **만료일 설계(고정 날짜 + 비대칭 폴백)만 개선 대상.**
> 원칙 불변: 자동 해제·자동 완화 없음. 이번 작업도 전부 "재검토 알림"만 추가하며, 캡/스코프를 자동으로 바꾸지 않는다.

## 1. 발견한 문제 (코드 근거)

### A. 모듈 간 만료 처리 불일치 (버그)

- `src/compass/regime_engine.py::_manual_regime_effective()`: `as_of > regime_expires_date`면 override를 **None으로 반환 → 컴퓨티드 레짐(CRISIS)으로 자동 대체**. TAA tilt(`saa_profiles.yaml`)는 이 경로를 타므로 만료 시 CRISIS 수준 방어 tilt(kr_alpha -15%p 등)가 걸림.
- `src/policy_cap.py::resolve_policy_cap()`: `market.regime`(CSV 원본 값)을 **만료 여부와 무관하게 그대로 사용**. `is_expired=True`가 되어도 `cap_regime`/`max_execution_scope`는 계속 YELLOW_STABLE→ETF_ONLY로 계산됨 (`expiry_status="EXPIRED_REVIEW_REQUIRED"`라는 경고만 추가될 뿐, capped scope 자체는 안 바뀜).
- 결과: 9/24 이후 원장님이 갱신을 놓치면 **TAA tilt는 CRISIS 수준으로 방어적으로 바뀌는데, 실행 scope 캡은 여전히 (만료된) YELLOW_STABLE 기준 ETF_ONLY에 머무는 내적 불일치 상태**가 됩니다. 이건 "더 세짐"도 "그대로 유지"도 아닌, 두 모듈이 서로 다른 전제로 계산하는 버그입니다.

### B. 조건부 조기 재검토 트리거 부재

현재 재검토를 유발하는 신호는 시간 기반 둘뿐:
- `AC-05`: override 설정 후 5영업일 경과 시 고정 `warn` (그 이후 60일이 지나도 동일한 `warn` — 심각도 단계 없음)
- `AC-05b`: 산출-적용 레짐 격차(gap)가 임계 이상으로 3일 연속일 때 escalate

**시장이 실제로 크게 움직였을 때**(추가 급락, 또는 반대로 회복) 반응하는 경로가 없습니다. 예: KOSPI가 -25%에서 -35%로 더 빠지거나, 반대로 -25%에서 -10%(crisis 임계 상회)로 회복해도, gap 임계·영업일 카운트가 갱신되지 않는 한 아무 알림도 없습니다.

### C. AC-05 심각도 미단계화

`_check_regime_override()`는 5영업일 초과 시 무조건 `warn` 한 단계뿐. 6일째나 60일째나 동일한 문구입니다. AC-05b처럼 "장기 방치"를 별도로 구분하는 승격 단계가 없습니다.

## 2. 승인된 작업 범위

### A. `policy_cap.py` 만료 시 컴퓨티드 레짐으로 폴백 (버그 수정)

`resolve_policy_cap()`이 `is_expired=True`일 때, `regime_engine.py`와 동일하게 **컴퓨티드 레짐을 기준으로 `cap_regime`/`max_execution_scope`를 재계산**하도록 수정. 두 모듈이 만료 시 동일한 전제(컴퓨티드 레짐)로 수렴해야 함. `resolve_policy_cap()` 호출 시 컴퓨티드 레짐 값을 인자로 받을 수 있게 시그니처 확장(이미 계산돼 있는 `compass_regime.json`의 `computed_regime`을 전달).

### B. 조건부 조기 재검토 트리거 추가

`src/validation/regime_override_divergence.py` 또는 신규 모듈에 다음 두 조건을 추가:

- **추가 악화 트리거**: override 설정일(`regime_set_date`) 시점의 KOSPI 낙폭 대비, 현재 낙폭이 `early_review_worsening_dd_delta_pct`(기본 -5.0%p) 이상 추가 악화되면 즉시 `warn` — AC-05b의 3일 연속 조건과 무관하게 당일 발동.
- **회복 트리거**: 낙폭이 `early_review_recovery_dd_threshold`(기본 -15.0%, `risk_off_drawdown`과 동일 값 재사용)보다 좋아지면(즉 crisis 임계를 벗어나면) `info`(재검토 후보) 알림 — "조건이 개선됐으니 원한다면 완화 검토 가능"이라는 의미. **자동 완화 아님. 사람이 검토해야 갱신.**

두 트리거 모두 `compass_rules.yaml`에 파라미터화하고, 기존 원칙대로 **경고만 생성, override/cap 자동 변경 없음**.

### C. AC-05 심각도 단계화

`_check_regime_override()`의 5영업일 고정 임계를 AC-05b와 동일한 패턴으로 확장:
- 5영업일 초과: 기존과 동일 `warn`
- `override_age_escalation_days`(기본 15영업일) 초과: `warn` 유지하되 메시지를 "장기 미검토 — 재검토 시급"으로 승격 (fail로 올리지 않음, 실행 차단 원칙 불변)

## 3. 절대 금지 (변경 없음)

- override 자동 해제, 자동 갱신, 자동 만료일 연장 — 전부 사람이 수동으로 갱신.
- `_manual_regime_effective()`의 만료 시 컴퓨티드 레짐 폴백 로직 자체 — 이건 유지, `policy_cap.py`를 여기에 맞추는 것.
- `execution_scope.py`, `core_deployment_throttle.py`, `execution_guards.py`의 게이트 임계값.
- AC-05/AC-05b를 `fail`로 승격하는 것 — 계속 `warn`까지만, 실행을 자동 차단하지 않음(사람 승인 경로는 불변).
- 캡의 폭(`_POLICY_MAX_SCOPE` 테이블) 자체 — 이번 범위 아님(이미 방어 가능하다고 판단).

## 4. 검증 요청

1. A 수정 후: `regime_expires_date`를 과거로 강제 설정한 합성 fixture로 `policy_cap.py`와 `regime_engine.py`가 **동일한 컴퓨티드 레짐**을 반영하는지 (cap이 CRISIS→NO_TRADE로 일치하는지) 단위 테스트.
2. B 악화 트리거: `regime_set_date` 시점 낙폭과 현재 낙폭 차이가 -5%p 이상인 합성 케이스에서 즉시 warn 발동 확인.
3. B 회복 트리거: 낙폭이 -15% 상회(개선)로 돌아온 합성 케이스에서 info 알림 발동 확인 — 이때 override/cap 값 자체는 변경되지 않았음을 함께 확인(자동 완화 없음 증명).
4. C: override_age를 6일/16일 두 케이스로 나눠 메시지 승격 여부 확인.
5. 기존 AC-05/AC-05b 정상 케이스(현재 라이브 데이터, gap=3·연속 2일·13영업일 경과)에서 회귀 없는지 재실행 결과 첨부.
6. 이번 수정으로 인해 오늘자 라이브 판정(NO_TRADE, ETF_ONLY 등)이 바뀌지 않는지 — 바뀐다면 그 이유를 반드시 별도 명시.
