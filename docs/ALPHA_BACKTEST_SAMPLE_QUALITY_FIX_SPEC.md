# Alpha 백테스트 표본 라벨링 — 수정 승인 명세서

> 근거: Claude 독립 검증 (이 문서 자체가 조사 결과 겸 수정 명세 — 별도 INVESTIGATION 문서 없음)
> 발견: `outputs/alpha_backtest_report.md`/`alpha_backtest_summary.csv`(2026-07-13 20:08 생성)가
> "사용 일수: 270일 · 품질: provisional"이라 표시하지만, 실제로 스코어링에 기여한 날짜는
> **최대 17일**(2026-06-17~2026-07-09)로 추정됨. 라벨이 신뢰도를 심하게 부풀리고 있음.
> 운영자 결정: **라벨/표본수 정확화만 진행. 진짜 과거 PIT 재무 히스토리 구축(옵션 b)은 이번 범위 아님.**
> 결과 수치(top_n_excess 등) 자체의 재계산·재설계는 이번 범위 아님.

## 1. 문제의 근본 원인 (코드 근거)

- `data/fundamentals.csv`: 종목당 1행뿐 (2,727종목 전수 확인, 중복 0건) — 시계열이 아니라 **단일 현재 스냅샷**.
- `usable_from_date` 값이 딱 2가지뿐: `2026-06-17`(2,721종목), `2026-07-08`(6종목).
- `data/prices_history.csv`: 270개 고유 날짜, 범위 2025-06-04~2026-07-09. 이 중 **253일(93.7%)이 2026-06-17 이전**.
- `src/alpha/data_gate.py::apply_data_gate()`: `as_of_dt < usable_dt`면 해당 종목 제외 → 2026-06-17 이전 날짜는 **전 종목이 게이트에서 걸러짐** → `usable` 딕셔너리 공집합.
- `src/backtest/alpha_backtest.py::_score_on_date()`: `scored_universe = [u for u in passed if u.ticker in usable]`가 공집합이면 `len(scored_universe) < 5`로 빈 DataFrame 반환.
- `run_alpha_lite_backtest()` 133행: `result.dates = dates`가 **게이트 통과 여부와 무관하게** 원본 가격 이력의 고유 날짜 리스트 전체(270개)를 그대로 담음.
- 188행: `result.sample_quality = sample_quality_label(len(result.dates))` — **원본 270을 그대로 품질 라벨 산정에 사용**. 실제로 스코어링에 기여한 날짜 수가 아님.
- `write_alpha_backtest_outputs()`의 `dates_used: len(result.dates)`도 동일하게 270을 그대로 출력.

결론: "270일 사용 / provisional" 이라는 표시는 **원본 가격 데이터 범위**를 뜻할 뿐, 실제로 top_n/quintile 계산에 들어간 날짜 수와 무관하다. 이 괴리가 보고서 사용자(운영자)에게 실제보다 훨씬 신뢰도 높은 검증처럼 보이게 만든다.

## 2. 승인된 작업 범위

### A. 실제 기여 날짜를 별도로 추적

`run_alpha_lite_backtest()` 루프 내부에서, `scored`가 비어있지 않고 `len(scored) >= 5`이며 quintile 계산(`pd.qcut`)까지 성공한 날짜만 별도 리스트(예: `result.scored_dates`)에 추가. 기존 `result.dates`(원본 가격 이력 범위)는 그대로 유지하되 의미를 "가격 데이터 커버리지"로 명확히 구분.

### B. 품질 라벨 산정 기준 교체

`result.sample_quality = sample_quality_label(len(result.dates))` →
`result.sample_quality = sample_quality_label(len(result.scored_dates))`로 변경.

### C. 출력에 두 숫자를 모두 명시

`alpha_backtest_summary.csv`, `alpha_backtest_report.md` 양쪽에:
- `price_history_days`(원본 270) — 참고용, 라벨 근거 아님을 명시
- `scored_days_used`(실제 기여 일수) — **이 숫자가 품질 라벨의 근거임을 명시**

두 숫자 차이가 클 때(예: `scored_days_used / price_history_days < 0.3`) 경고 문구 추가:
`"PIT 재무 데이터가 단일 스냅샷(usable_from_date 종류 {N}개)이라 유효 표본이 가격 데이터 범위 대비 크게 작음 — 결과를 전략 판단 근거로 사용하지 말 것"`

### D. 계산 로직 자체는 불변

top_n_avg_return, universe_avg_return, quintile 수치 등 **실제 반환값 계산 로직은 절대 건드리지 말 것**. 이번 수정은 순수하게 "몇 개 날짜가 실제로 계산에 들어갔는지 정확히 세고 정직하게 라벨링"하는 투명성 수정이다.

## 3. 절대 금지 (변경 없음)

- `_score_on_date()`, `score_factors()`, `apply_penalties()`, `assign_grades()` 등 스코어링 로직.
- `data_gate.py`의 PIT 게이트 임계값(`require_point_in_time`, `stale_data_max_days`).
- `cost_assumptions.yaml` 비용 가정치.
- 진짜 과거 재무 스냅샷을 새로 구축하는 작업 — 이번 범위 아님 (별도 논의 필요).
- gate / policy_cap / execution_scope / dry_run 등 실행 게이트 — 이 백테스트는 원래도 그쪽에 영향 없음, 계속 무관하게 유지.

## 4. 검증 요청

1. 수정 전/후 `top_n_avg_return`, `universe_avg_return`, `top_n_excess`, quintile 수치가 **완전히 동일**한지 확인 (계산 로직 불변 증명).
2. 재실행 후 `scored_days_used` 실제 값 보고 (예상: 17 이하).
3. `sample_quality` 라벨이 바뀌는지 확인 (예상: provisional → insufficient 또는 그에 준하는 하향).
4. 경고 문구가 실제로 report.md에 나타나는지 확인.
5. 단위 테스트 추가: 합성 fixture로 (a) 가격 이력 30일, 그중 usable_from_date가 마지막 5일에만 걸리는 케이스를 만들어 `scored_days_used == 5`, `price_history_days == 30`이 되는지 검증.
