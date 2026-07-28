# 레짐 오버라이드 격차(divergence) 경고 추가 — 명세서

> 배경: 검증자 발견 — `computed_regime`(산출)과 `applied_regime`(적용) 사이 격차를 감시하는 장치가 없음
> 현재 사례: 산출=`CRISIS`, 적용=`YELLOW_STABLE` (5단계 중 `CAUTION`·`RISK_OFF` 두 단계를 건너뛰는 최대폭에 가까운 격차)
> 범위: **경고(가시성) 추가만** — 오버라이드 자동 해제, 정책 캡, execution_scope, throttle 로직 변경 없음

## 1. 문제 정의

`src/compass/models.py`의 `RiskRegime`은 심각도 순으로 다음과 같이 정의돼 있음:

```
RISK_ON(0) < YELLOW_STABLE(1) < CAUTION(2) < RISK_OFF(3) < CRISIS(4)
```

`src/compass/regime_engine.py`의 `compute_compass()`는 사람이 설정한 `manual_regime`(만료일 이전이면)을 `computed_regime`(가격 데이터로 산출한 값) 대신 `applied_regime`으로 사용한다. 지금 상태:

- `computed_regime`: `CRISIS` (코스피 최근 고점 대비 낙폭이 crisis 임계 -15%를 초과해서 산출됨)
- `applied_regime`: `YELLOW_STABLE` (2026-06-24 설정된 수동 오버라이드, BOK FSR 근거, 만료 2026-09-24)
- 격차: 4단계 척도에서 3칸 차이 (거의 최대치)

`src/validation/system_health.py`의 `regime_computed` 체크는 `computed_regime` 값이 존재하는지만 pass/fail로 보고, 두 값을 `"산출=X 적용=Y"`로 표시만 할 뿐 **격차 크기에 대한 판정이 없다.** 시간 기반 경고(`AC-05`, override 경과일수)는 있지만 격차 크기 기반 경고는 없다.

## 2. 요구사항

`computed_regime`과 `applied_regime`이 크게 벌어졌을 때 — 특히 **오버라이드가 리스크를 낮추는 방향**(산출이 적용보다 더 심각할 때)일 때 — 명시적으로 눈에 띄는 경고를 추가한다.

### 2.1 격차 계산

- `RiskRegime` 순서에 서수(0~4)를 매겨 `severity(regime)` 함수 작성 (또는 기존에 유사 매핑이 있으면 재사용).
- `gap = severity(computed_regime) - severity(applied_regime)` (오버라이드가 아닐 때는 0).
- **양수 gap**(산출이 적용보다 심각) 방향에 우선순위를 둠 — 이게 "위험을 완화한 오버라이드" 방향이라 더 중요.

### 2.2 임계값 및 경고 단계

- `gap >= 2`: 경고(warn) — 예: 지금 사례(gap=3)는 여기 해당.
- `gap >= 1` (즉 1단계라도 완화): 정보성 표시(현재도 있는 "산출=X 적용=Y" 문구 유지, 추가 조치 없음).
- 이 임계값은 하드코딩하지 말고 설정값으로 분리 (`gate_thresholds` 유사 위치, 또는 `regime_rules`에 추가).

### 2.3 추가 위치 (택1 또는 병행, 조사 후 적합한 곳 선택)

- `src/validation/acceptance_check.py`: `AC-05`(manual_regime) 옆에 신규 항목(예: `AC-05b regime_override_divergence`)으로 추가 — 시간 기반 경고와 크기 기반 경고를 구분해서 노출.
- `src/validation/system_health.py`: `regime_computed` 체크의 `status`를 격차 기준으로 `pass`/`warn` 분기하도록 확장.
- 두 곳 다 건드릴 경우 문구·로직 중복 없게 공통 함수로 추출 권장.

### 2.4 경고 메시지 요건

- gap 값, computed_regime, applied_regime, override 근거(`regime_override_reason`), override 설정일(`regime_set_date`)을 모두 포함.
- "이건 오버라이드가 틀렸다는 뜻이 아니라, 산출값과 적용값의 격차가 크니 재확인이 필요하다"는 취지를 명확히 하는 문구 (운영자 판단을 대체하는 게 아니라 보조하는 경고임을 명시).

## 3. 절대 금지

- gap이 크다고 오버라이드를 **자동으로 해제하거나 값을 바꾸지 말 것** — 순수 경고/가시성 추가만. 오버라이드 적용 여부는 여전히 운영자 판단.
- `regime_engine.py`의 `_classify_risk_regime()`, `_manual_regime_effective()` 등 레짐 산출·적용 로직 자체는 변경 금지 (계산 방식은 그대로, 결과를 감시하는 계층만 추가).
- `policy_cap`, `execution_scope`, `core_deployment_throttle`, `execution_guards` 변경 금지.

## 4. 검증 요청

1. 단위 테스트: `computed=CRISIS, applied=YELLOW_STABLE` (gap=3) → warn 발생 확인.
2. 단위 테스트: `computed=CAUTION, applied=YELLOW_STABLE` (gap=1) → warn 미발생(정보성만) 확인 — 과경보 방지.
3. 단위 테스트: `computed=applied` (gap=0) → 아무 경고 없음.
4. 기존 `AC-05`(시간 기반) 동작에 회귀 없는지 확인.
5. 재실행 후 현재 라이브 데이터(computed=CRISIS, applied=YELLOW_STABLE)로 실제 경고가 뜨는지 최종 확인, 스크린샷/출력 첨부.
