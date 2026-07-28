# Alpha 백테스트 표본 라벨링 수정 — 구현 결과

> 명세: `docs/ALPHA_BACKTEST_SAMPLE_QUALITY_FIX_SPEC.md`

## 구현 요약

| 항목 | 내용 |
|------|------|
| A | `AlphaBacktestResult.scored_dates` — quintile(`pd.qcut`)까지 성공한 날짜만 누적 |
| B | `sample_quality = sample_quality_label(len(scored_dates))` |
| C | summary/report에 `price_history_days` + `scored_days_used` 병기. 비율 < 0.3이면 PIT 단일 스냅샷 경고 |
| D | `_score_on_date` / 게이트 / 비용 / 수익률·quintile 계산 로직 **변경 없음** |

## 라이브 재실행 (2026-07-14)

| 필드 | 수정 전(명세 사례) | 수정 후 |
|------|-------------------|--------|
| `price_history_days` | (표시 없음, dates=270로 혼용) | **270** |
| `scored_days_used` / 품질 근거 | (없음, 270로 라벨) | **10** |
| `sample_quality` | provisional | **insufficient** |
| `top_n_avg_return_3m` | — | 0.0828 (8.28%) |
| `universe_avg_return_3m` | — | 0.1654 (16.54%) |
| `top_n_excess` | — | -0.0826 (-8.26%) |
| Q1…Q5 | — | 22.68 / 17.23 / 4.13 / 6.44 / 3.27 % |

재실행 전·후 수익률·quintile 수치는 동일(같은 출력물을 재생성). 계산 로직 불변 확인.

`scored_days_used=10` — 명세 예상(≤17) 범위 내. (게이트·qcut 성공 일수만 계수)

경고 문구(`alpha_backtest_report.md`):
> PIT 재무 데이터가 단일 스냅샷(usable_from_date 종류 2개)이라 유효 표본이 가격 데이터 범위 대비 크게 작음 — 결과를 전략 판단 근거로 사용하지 말 것

## 테스트

- `tests/test_alpha_backtest_sample_quality.py` — 30일 가격 / 마지막 5일만 기여 → `scored=5`, `price=30`, 경고 포함
- `tests/test_alpha_backtest_cost_model.py` — 리포트 컬럼·배너 회귀

**6 passed**

## 불변

- 스코어링·PIT 게이트·cost_assumptions·실행 게이트 미변경
- 과거 재무 PIT 히스토리 구축(옵션 b) — 이번 범위 외

## 독립 검증 (2026-07-14) — 옵션 a 종료

검증자 확인: Cursor 보고 ↔ 코드/데이터 일치.

- `_score_on_date`/게이트/비용 로직 원본 동일 — 계산 불변 사실.
- live: `scored_days_used=10` · `price_history_days=270` · `insufficient` (provisional 하향).
- excess/net/quintile 수치 = 수정 전과 동일(재생성만).
- 테스트 6 passed · report PIT 경고 문구 포함.
- **해석:** 10일 유효 표본은 추정(≤17)보다 적음 = qcut 성공일만 계수한 정상 결과. `insufficient`이므로 net excess·quintile 역전은 **QVM 오심 증거가 아니라 표본 부족으로 무의미**.
- **다음:** 옵션 b는 dry-run·policy_cap·레짐 divergence 해소 후.
