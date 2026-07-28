# 경제 나침반 — 방법 B 백테스트 결과 요약

> SPEC: [`ECONOMIC_COMPASS_METHOD_B_BACKTEST_SPEC.md`](ECONOMIC_COMPASS_METHOD_B_BACKTEST_SPEC.md)  
> 산출물: `outputs/backtest/compass_method_b_*`  
> 실행: `python scripts/run_compass_method_b_backtest.py`

## 한 줄 결론

**SAA+TAA가 정적 SAA 대비 통계적으로 유의한 초과수익을 내지 못함** (excess DSR≈0.006).  
다만 TAA 경로는 **변동성·MDD가 소폭 개선**되었고(Sharpe 1.14→1.20, MDD −17.9%→−15.4%), CRISIS 구간 누적 초과는 양수(+0.017)였음.  
스펙대로 **비유의 결과도 그대로 보고**하며, 이 결과만으로 `compass_rules.yaml`을 조정하지 않음.

## 검증 체크리스트

| # | 항목 | 결과 |
|---|---|---|
| 1 | 윈도우·행 수 | Panel **2015-01-02~2026-07-15**, **2831행**; judgment start **2015-10-23** (워밍업 200거래일) |
| 2 | 기존 로직 import | `compute_compass` / `build_portfolio_allocation` / `_compute_kospi_metrics` 재사용. Method B 코드는 `src/backtest/compass_method_b/`·script만 추가 |
| 3 | PIT / 미래 유출 | `judgment_history`는 시점 t 계산 시 **t 이전만** 전달. 수동 검산: 2017-11-07 기준 hist_last=2017-11-06, n=500 |
| 4 | §4 통계검정 | DSR(excess/TAA) + IS/OOS(2021-01-01) 수치 보고 (`compass_method_b_report.md` §4) |
| 5 | 데이터 한계 명시 | tier2 제외 · foreign_flow=`neutral` · korea_10y=FRED `IRLTLT01KRM156N` 월간 ffill · 그룹 수익률 프록시 |

## 핵심 수치

| | Static SAA | SAA+TAA |
|---|---:|---:|
| Cum | 145.77% | 140.47% |
| CAGR | 9.00% | 8.77% |
| Vol | 7.83% | 7.21% |
| MDD | −17.89% | −15.39% |
| Sharpe | 1.140 | 1.203 |

- Excess ann (TAA−SAA): **−0.26%** (daily mean −1.0e-5, SE 1.4e-5)
- **DSR(excess, n_trials=16): 0.0060** — 유의하지 않음
- PSR(excess vs 0): 0.237
- Regime flips: **210** (일별 관측 ≠ 독립 사이클)
- IS(2015–2020) excess ann −0.21% / OOS(2021–) −0.30% · same-sign **True** · 양쪽 DSR 모두 낮음

## Korea 10Y 시리즈 확정

FRED 검색으로 **`IRLTLT01KRM156N`** (Interest Rates: Long-Term Government Bond Yields: 10-Year, Korea, Monthly) 채택. 일별로 forward-fill.

## 산출물 목록

- `outputs/backtest/compass_method_b_input.csv`
- `outputs/backtest/compass_method_b_results.csv`
- `outputs/backtest/compass_method_b_nav_path.csv`
- `outputs/backtest/compass_method_b_judgment_log.jsonl`
- `outputs/backtest/compass_method_b_report.md`
- `outputs/backtest/compass_method_b_meta.json`

## 다음 (로드맵)

- 방법 B 결과만으로 tilt_scale/임계값 **즉시 변경 금지** (SPEC §7).
- 라이브 로그(방법 A) 축적 · 2단계 Turbulence 게이트(60행)는 별트랙 유지.
- 유의미한 개선 없이도 “검증 불가/비유의”는 의사결정 입력으로 유효 — 4단계 논의 시 이 RESULT를 기준점으로 사용.
