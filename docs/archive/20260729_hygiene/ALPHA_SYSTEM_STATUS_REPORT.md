# 알파 시스템 — 상태 리포트

- as_of: `2026-07-16`
- window_end: `2027-12-31`
- days_to_window_end: **533**
- capital_max_fraction: `0.3`
- score_cutoff: `None`

## 트랜치 상태

| tranche | state | trigger_met | weight | detail |
|---|---|---|---:|---|
| T1 | READY | True | 0.25 | time: system_started |
| T2 | PENDING | False | 0.25 | event: event_ids [TODO] empty — trigger cannot fire |
| T3 | PENDING | False | 0.25 | price: valuation_band [TODO] unset — trigger cannot fire |
| T4 | PENDING | False | 0.25 | hybrid: hybrid_rules [TODO] unset — trigger cannot fire |

## 트리거·액션 (이번 평가)

| type | tranche | reason |
|---|---|---|
| MARK_READY | T1 | time: system_started |

## 종목 스코어 · eligibility

_스코어 스냅샷 없음._

## 성과 추적

- fills recorded: **0**
- benchmark: `None` ([TODO] unset — comparison hook only)

_집행 단가 기록 없음._

## 재량 이탈 (WARN_DISCRETIONARY)

- 누적 횟수: **0**

이탈이 반복되면 운용자 문제가 아니라 **규칙이 현실과 안 맞는다**는 신호로 읽는다.

_기록 없음._

## Warnings

- T2: event: event_ids [TODO] empty — trigger cannot fire
- T3: price: valuation_band [TODO] unset — trigger cannot fire
- T4: hybrid: hybrid_rules [TODO] unset — trigger cannot fire
