# 레짐 격차 지속일 기반 재확인 재촉 — 명세서

> 배경: `docs/REGIME_OVERRIDE_DIVERGENCE_ALERT_SPEC.md`(이미 구현·검증됨)의 확장.
> 지금은 격차(gap)가 커도 사람이 직접 acceptance/health를 열어봐야만 알 수 있고, 재확인 시한은 여전히 `regime_expires_date`(최대 3개월 뒤)뿐임.
> 목적: **격차가 며칠째 지속되는지 추적**해서, 오래 방치될수록 더 일찍·더 강하게 재확인을 재촉한다.
> 범위: **경고 강도·재확인 권고 시한 표시만** — 오버라이드 자동 해제, 실행 게이트, policy_cap/execution_scope/throttle **변경 없음** (기존 원칙 그대로 승계).

## 1. 요구사항

### 1.1 지속일 추적

- 신규 로그: `outputs/regime_divergence_log.jsonl` — 매일 파이프라인 실행 시 그날의 `date`, `computed_regime`, `applied_regime`, `gap`, `override_active`를 한 줄 append (날짜 중복 시 스킵 — `dry_run_log.jsonl`과 동일한 패턴 재사용).
- `src/validation/regime_override_divergence.py`에 함수 추가: `count_consecutive_divergence_days(log_path, *, warn_gap, as_of) -> int` — 로그를 최신 날짜부터 역순으로 스캔하며, `override_active and gap >= warn_gap`을 만족하는 연속 일수를 센다(조건이 깨지는 순간 중단).

### 1.2 에스컬레이션 임계값

- `data/compass_rules.yaml` → `regime_rules.override_divergence_escalation_days` (기본값 3, 영업일이 아니라 로그에 기록된 날짜 수 기준으로 단순화해도 무방 — 조사 후 결정).

### 1.3 에스컬레이션 동작

- `consecutive_days < escalation_days`: 기존 `AC-05b` 경고 그대로 (변경 없음).
- `consecutive_days >= escalation_days`:
  - 메시지에 "N일째 지속" 명시.
  - `recommended_review_by` 필드 추가: `today + review_buffer_days`(설정값, 기본 2) — `regime_expires_date`(9월 24일 등)와는 별개로, "이 정도 지속됐으면 이 날짜 전에는 재확인하는 게 좋다"는 **권고용 표시**. 실제 `regime_expires_date`는 건드리지 않음.
  - `status`는 여전히 `warn` 유지(요건: 실행 게이트에 영향 주지 않음 — `fail`로 격상하지 말 것). 다만 message/detail에 긴급도가 더 드러나야 함.

### 1.4 위치

- `assess_regime_override_divergence()`를 확장하거나, 별도 `assess_regime_divergence_persistence()`를 만들어 기존 함수 결과에 지속일 정보를 합성. 기존 `AC-05b`/`system_health.regime_computed` 호출부에서 이 확장 결과를 사용하도록 연결.
- 로그 append는 일간 파이프라인(예: `scripts/daily_pipeline.py` 또는 compass 실행 지점) 어디에 훅을 거는 게 자연스러운지 조사 후 결정 — `dry_run_log.jsonl` append 지점을 참고.

## 2. 절대 금지 (기존과 동일)

- 오버라이드 자동 해제·값 변경 없음.
- `regime_engine.py`의 산출 로직 변경 없음.
- `policy_cap`, `execution_scope`, `core_deployment_throttle`, `execution_guards` 변경 없음.
- 에스컬레이션이 `fail`이나 실행 차단으로 이어지지 않게 할 것 — 어디까지나 "더 눈에 띄게 재촉"이지 "자동 개입"이 아님.

## 3. 검증 요청

1. 단위 테스트: 합성 로그로 연속 3일 gap≥2 → 에스컬레이션 메시지·`recommended_review_by` 발생 확인.
2. 단위 테스트: 중간에 하루라도 gap<threshold 또는 override_active=false면 카운트 리셋되는지 확인.
3. 단위 테스트: 로그 파일 없음/1일치만 있음 → 에스컬레이션 미발생, 기존 AC-05b 동작 유지.
4. 라이브 데이터로: 지금 상황(override 2026-06-24부터 지속)을 로그에 소급 반영했을 때 실제로 에스컬레이션이 뜨는지 확인 — 단, 로그가 없던 과거 날짜를 인위적으로 채워 넣지 말고, "로그 시작 시점부터 카운트"라는 한계를 명시할 것(과거 데이터 조작 금지, 오늘부터 정직하게 쌓는 것이 원칙 — dry-run 카운트와 동일 원칙).
5. `AC-05`(시간 기반), `AC-05b`(격차 기반) 기존 테스트 회귀 없는지 확인.
