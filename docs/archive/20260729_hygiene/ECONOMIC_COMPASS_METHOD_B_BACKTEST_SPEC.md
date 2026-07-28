# 경제 나침반 — 방법 B(외부 장기데이터 백테스트) 본 스펙

> ROADMAP: [`ECONOMIC_COMPASS_ROADMAP.md`](ECONOMIC_COMPASS_ROADMAP.md) §"검증 방법 후보" B
> 데이터 가용성: [`ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_RESULT.md`](ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_RESULT.md) — FRED·Yahoo·KOSPI(KRX 자격증명 기설정) 전부 확인됨.
> 원칙: **기존 판정 로직 재사용, 재구현 금지.** `score_growth`/`score_inflation`/`score_liquidity`/`score_risk_appetite`/`classify_market_phase`/`_classify_risk_regime`/`apply_regime_hysteresis`/`apply_phase_hysteresis`를 그대로 import해서 과거 데이터에 돌린다 — 백테스트용으로 로직을 별도로 다시 짜면 "백테스트 따로, 실전 따로"가 되어 검증 의미가 없어짐.
> 이 스펙은 **새 산출물을 만드는 것**이지 운영 코드(`portfolio_builder.py`, `regime_engine.py` 등)를 수정하는 게 아님 — 신규 스크립트/모듈만 추가.

## 0. 목적

`src/backtest/regime_backtest.py`는 현재 배분 경로만 추적하고 실제 수익률을 측정하지 않음(자체 명시: "수익률 예측 아님"). 이 스펙은 그 구멍을 메운다 — 2015~현재(약 11.5년) 실데이터로 나침반이 과거에 어떤 판정을 내렸을지 소급 계산하고, 그 판정을 따랐을 때 실제로 SAA 고정 배분보다 나았는지를 처음으로 측정한다.

## 1. 데이터 구성

### 1.1 소스별 시리즈

| 필드 | 소스 | 세부 |
|---|---|---|
| kospi (종가) | pykrx `get_index_ohlcv_by_date`, 코드 "1001" | 확인된 자격증명으로 2015-01-02~현재 fetch (2831행 확인됨) |
| kospi_recent_high, kospi_200ma | **직접 계산 금지 — 기존 함수 재사용** | `src/data_refresh/market_indicators_refresh.py::_compute_kospi_metrics()`를 그대로 import해서 매 시점 롤링 적용 (해당 함수의 recent_high=누적 max, 200ma=tail(200).mean() 정의를 그대로 따름 — 백테스트가 라이브와 다른 정의를 쓰면 결과가 무의미해짐) |
| sp500, sp500_recent_high | Yahoo `^GSPC`, `interval=1d&range=3650d`(또는 그 이상) | 동일하게 `_compute_kospi_metrics`류 로직(모듈 내 대응 함수 있으면 그것, 없으면 동일 산식 별도 함수화하되 로직은 동일하게) 적용 |
| vix | Yahoo `^VIX` | 그대로 사용 |
| usdkrw | Yahoo `KRW=X` | 그대로 사용 |
| oil_brent | Yahoo `BZ=F` | 그대로 사용 |
| gold | Yahoo `GC=F` | 그대로 사용 |
| korea_10y | FRED (적절한 한국 10년물 시리즈 ID 확인 필요 — `IRLTLT01KRM156N` 등 후보, Cursor가 FRED API로 직접 검색해 확정) | 없으면 이 축만 결측 처리하고 한계로 명시 |
| foreign_flow_3d | **장기 이력 확보 어려울 가능성 높음** | pykrx에 외국인 순매수 일별 데이터 있으면 사용, 없으면 "neutral" 고정값으로 근사하고 **이 축의 백테스트 정확도가 낮다는 걸 결과 보고서에 명시** |
| tier2(PMI/CPI/HY스프레드 등) | **이번 백테스트에서 제외** | `compute_compass(..., tier2=None)`으로 호출 — 장기 tier2 이력 확보가 더 어려우므로 1차 백테스트는 tier1(4축) 로직만으로 진행. tier2 포함은 후속 과제로 남김 |

### 1.2 저장 위치

`outputs/backtest/compass_method_b_input.csv` — 신규 파일, 운영 `data/market_indicators*.csv`와 분리(백테스트 입력을 운영 데이터와 섞지 않음).

### 1.3 결측·이상치 처리

- 각 소스의 시작일이 다르므로(KOSPI 2015-01-02, Yahoo 소스별 상이) **전 지표가 공존하는 교집합 구간**을 최종 백테스트 윈도우로 확정하고 보고서에 정확한 시작일 명시.
- 200일 이동평균 계산을 위해 최소 200거래일치 워밍업 구간이 필요 — 백테스트 "판정 시작일"은 데이터 시작일 + 200거래일 이후로 설정.

## 2. 재현 로직

1. 일별(또는 주별 — 아래 §4 참고)로 시점 t까지의 데이터로 `MarketIndicators` 객체 구성(과거 시점 기준, 미래data 유출 금지 — 워크포워드 원칙: t 시점 계산엔 t 이전 데이터만 사용).
2. `compute_compass(market_t, rules, tier2=None, output_dir=..., judgment_history=이전_판정들)` 그대로 호출 — 즉 `src/compass/regime_engine.py`를 신규 백테스트 스크립트에서 **import해서 그대로 사용**.
3. 매 시점 결과(`computed_regime`, `applied_regime`, `market_phase`, tilt 등)를 백테스트 전용 로그(`outputs/backtest/compass_method_b_judgment_log.jsonl`)에 누적 — 이게 곧 `judgment_history` 인자로 다음 시점에 재사용됨(실제 히스테리시스 로직이 과거 시점 자신의 로그를 보고 판단하는 구조를 그대로 재현).
4. `data/compass_rules.yaml`의 현재 운영 값(tilt_governance, hysteresis 포함)을 그대로 사용 — 백테스트용으로 임계값을 따로 튜닝하지 않음(중요: 만약 이 백테스트 결과를 보고 임계값을 조정하고 싶어지면, 그건 새로운 in-sample 튜닝이 되어 뒤에 §5 통계검정으로 반드시 걸러야 함).

## 3. 성과 측정

### 3.1 비교 대상 포트폴리오

- **정적 SAA**: `data/saa_profiles.yaml`의 `core_absolute_return` 프로필 고정 비중을 전 기간 유지했을 때의 수익률.
- **SAA+TAA(나침반 반영)**: 매 시점 `build_portfolio_allocation()`(기존 함수 재사용)로 계산된 비중을 반영했을 때의 수익률.
- 자산군별 수익률은 각 그룹을 대표하는 벤치마크 시계열로 근사(예: domestic_beta→KOSPI, global_beta→S&P500, cash_short_bond→단기채 프록시 등) — 정확한 종목 단위가 아니라 그룹 단위 근사임을 보고서에 명시.

### 3.2 지표

- 기간 누적수익률, CAGR, 변동성, 최대낙폽(MDD), 샤프비율 — SAA 단독 vs SAA+TAA 비교.
- **초과수익(TAA − SAA)**과 그 표준오차.
- 국면/레짐별 평균 초과수익(예: CRISIS 판정 기간에 실제로 낙폭을 피했는지).

## 4. 통계적 유의성 검정 (필수 — 생략 금지)

- **표본 크기 명시**: 약 11.5년(2015~현재) 데이터가 확보 기준 30~100건 요구(일별 관측치 자체는 많지만, 독립적인 "국면 사이클" 수는 이 기간에 몇 번 안 됨 — 실제로 몇 번의 완전한 국면 전환이 있었는지 별도로 카운트해 보고).
- **다중검정 보정**: 이 시스템은 지표 8개×임계값 다수로 자유도가 15개 이상(Harvey-Liu-Zhu 기준 t-stat 2.0이 아니라 3.0 이상 요구) — 단순 t-검정 결과를 그대로 "유의하다"고 해석하지 말 것.
- **Bailey & López de Prado의 Deflated Sharpe Ratio** 적용 — 관측된 샤프비율이 자유도(파라미터 수)를 감안했을 때도 우연이 아닌지 검정.
- 가능하면 **Probability of Backtest Overfitting(PBO)**도 계산 — 최소한 in-sample/out-of-sample 구간을 나눠(예: 2015-2020 vs 2021-현재) 앞구간에서 좋아 보였던 패턴이 뒷구간에서도 유지되는지 확인.
- **결과가 통계적으로 유의하지 않아도 그대로 보고할 것** — "그럴듯해 보이지만 통계적으로 유의하지 않음"이라는 결론도 유효한 결과.

## 5. 산출물

- `outputs/backtest/compass_method_b_report.md` — 위 §3, §4 결과 전체.
- `outputs/backtest/compass_method_b_results.csv` — 시점별 판정·비중·수익률 원자료.
- `docs/ECONOMIC_COMPASS_METHOD_B_RESULT.md` — 요약 + 검증 체크리스트.

## 6. 검증 체크리스트 (원장 확인용)

1. 데이터 윈도우 시작일·종료일·행 수가 §1.3 기준과 일치하는지.
2. `compute_compass`/`build_portfolio_allocation`이 신규 코드로 재구현되지 않고 기존 모듈에서 import됐는지(git diff로 `src/compass/` 미변경 확인).
3. `judgment_history`가 매 시점 "그 시점까지의" 과거만 포함하는지(미래 데이터 유출 없는지) — 임의 시점 하나를 골라 수동 검산.
4. §4 통계검정이 실제로 계산되어 보고서에 수치로 나와 있는지(생략되지 않았는지).
5. tier2 제외·foreign_flow_3d 근사 등 데이터 한계가 보고서에 명시돼 있는지.

## 7. 절대 금지

- `src/compass/` 내 기존 함수 로직 변경 금지 — 백테스트는 순수 소비자(import)로만 동작.
- 백테스트 결과를 보고 `data/compass_rules.yaml`의 운영 임계값을 이 스펙 범위 안에서 바로 조정하지 않음 — 조정하고 싶으면 별도 논의(그 자체가 in-sample 튜닝이 되므로 반드시 out-of-sample 재검증 절차를 거쳐야 함).
- `outputs/backtest/`는 운영 `outputs/`의 실행 게이트(decision_log, target_write 등)에 영향을 주지 않는 별도 디렉토리로 격리.
