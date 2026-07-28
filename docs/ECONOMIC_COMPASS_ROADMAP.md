# 경제 나침반(Compass) 업그레이드 로드맵

> **목적**: 이 문서는 "잊지 않고 진행"하기 위한 단일 진행상황 기준점(single source of truth)이다.
> 단계가 끝날 때마다 이 문서의 **상태** 컬럼과 **최근 갱신** 섹션만 갱신한다 — 새 문서를 만들지 않는다.
> 배경: `docs/CODEBASE_CLEANUP_PHASE_0_1_2_SPEC.md`(코드베이스 정리)와 별개 트랙. 여기는 `src/compass/`(경제 나침반 = TAA 핵심 로직) 자체의 신뢰도 개선이 대상.
> 원칙(전 단계 공통): **삭제·전면 재작성 금지, 점진적 계측→검증 순서 유지**. `src/alpha/`(kr_alpha), `take_profit_thesis.py`는 이 로드맵 범위 밖.

## 상태 요약

| 단계 | 상태 | 시작일 | 완료일 | RESULT 문서 |
|---|---|---|---|---|
| 0. 계측 인프라 (tilt 축소 + 로그) | 완료 | 2026-07-16 | 2026-07-16 | [`ECONOMIC_COMPASS_PHASE_0_1_RESULT.md`](ECONOMIC_COMPASS_PHASE_0_1_RESULT.md) |
| 1. 히스테리시스 이식 (Bry-Boschan 최소지속기간) | 완료 (라이브 관찰 지속) | 2026-07-16 | 2026-07-16 | 동일 (0·1 통합 RESULT) |
| 2. 리스크오프 판정 보강 (Turbulence Index 병행) | 대기 (데이터 부족, 25행/60행) | — | — | [`ECONOMIC_COMPASS_PHASE_2_SPEC.md`](ECONOMIC_COMPASS_PHASE_2_SPEC.md) · [GATE_CHECK](ECONOMIC_COMPASS_PHASE_2_GATE_CHECK.md) |
| 3. 국채 임계값 재검토 (조건부 — 데이터 확보 시에만) | 대기 | — | — | — |
| 4. 실측 성과 검증 및 최종 결정 | 1차 완료(방법B) — 최종 결정은 보류 | 2026-07-16 | 2026-07-16(1차) | [`ECONOMIC_COMPASS_METHOD_B_RESULT.md`](ECONOMIC_COMPASS_METHOD_B_RESULT.md) |

**상태 값**: 대기 / 진행중 / 검증중 / 완료 / 보류(사유 기록) / 스킵(사유 기록)

## 배경 (왜 이 로드맵이 필요한가)

2026-07-15~16 세션에서 `src/compass/`(경제 나침반: `economic_phase.py`의 4축 가중합 점수 → `regime_engine.py`의 국면/방향 분류 → `taa_engine.py`/`portfolio_builder.py`의 실제 비중 tilt 반영)을 전수 검토한 결과:

- 가중치·임계값(`data/compass_rules.yaml`)이 전부 분석가 판단으로 하드코딩되어 있고, 통계적 피팅·백테스트 캘리브레이션 근거가 코드 어디에도 없음.
- 국면/레짐 전환에 히스테리시스(최소 지속기간, 진입/이탈 임계값 분리)가 전혀 없어, 하루치 VIX·낙폭 수치가 경계를 넘으면 바로 tilt가 뒤집힐 수 있음(whipsaw 구조적 가능).
- `src/backtest/regime_backtest.py`가 이 로직의 유일한 백테스트 코드인데 실행 이력이 없고(`outputs/`에 산출물 전무), 실행되어도 "수익률 예측 아님"을 자체 명시 — 즉 이 나침반이 실제로 도움이 됐는지 이 코드베이스 안에서는 증명도 반증도 안 된 상태.
- 그럼에도 이 나침반의 판정은 `data/saa_profiles.yaml`의 `taa_tilts`/`phase_tilts`를 통해 실제 비중을 최대 ±15%p(CRISIS 레짐 kr_alpha)까지 흔드는, 실전 자금에 영향을 주는 로직임.

결론: 폐기도 전면 재설계도 아닌 **"영향력 축소 + 계측 시작 → 데이터 쌓이면 재평가"** 방향으로 합의(2026-07-16).

## 단계별 정의

### 0단계 — 계측 인프라 (tilt 축소 + 판정 로그)
- 목표: 나침반이 틀렸을 때의 손실 노출을 줄이면서, 판정 자체(4축 점수·국면·레짐·방향·raw tilt·scaled tilt)를 매일 기록해 향후 검증 데이터를 쌓기 시작.
- 상세: `docs/ECONOMIC_COMPASS_PHASE_0_1_SPEC.md` §1.
- 다음 단계 진행 조건: 로그 스키마 확정 + 파이프라인 정상 실행 확인.

### 1단계 — 히스테리시스 이식 (Bry-Boschan 최소지속기간)
- 목표: 국면/레짐 전환에 최소 지속기간 조건을 추가해 whipsaw 감소.
- 상세: `docs/ECONOMIC_COMPASS_PHASE_0_1_SPEC.md` §2.
- 다음 단계 진행 조건: 과거 로그로 시뮬레이션 시 월평균 전환 횟수 감소 확인.

### 2단계 — 리스크오프 판정 보강 (Turbulence Index 병행)
- 목표: VIX 단일 임계값 외에 다자산 공분산 기반 turbulence score(마할라노비스 거리)를 별도 신호로 병행 계산·로깅.
- 착수 전제: 1단계 완료 + 최소 60~120일 가격 이력 데이터 품질 확인(`data/prices_history.csv` 과거 손실 이력 있었음 — 재확인 필요).
- 별도 스펙 문서는 1단계 완료 후 작성.

### 3단계 — 국채 임계값 재검토 (조건부)
- 목표: `korea_10y` 임계값(3.0/4.5, 현재 하드코딩)을 한국 경기순환 데이터 기반으로 재추정 시도.
- 착수 전제: 한국 경기순환 기준일(통계청 등) 데이터 확보 가능 여부 확인. **불가능하면 이 단계는 스킵하고 4단계로 이동** — 억지로 진행하지 않음.

### 4단계 — 실측 성과 검증 및 최종 결정
- 목표: 0단계 로그(축소 tilt 운영 실적) + `regime_backtest.py` 확장으로 "나침반을 따랐을 때 실제로 도움이 됐는가"를 처음으로 실측.
- 착수 전제: 0단계 로그 최소 수개월 누적. **단, 아래 "신뢰도 판단 기준선" 참고 — 실시간 로그만으로는 기관급 검증에 수년 소요되므로, 장기 외부 과거데이터 백테스트를 병행하는 방안을 검토 중(§ 검증 방법 후보).**
- 갈림길:
  - 긍정적 신호 확인 → tilt_scale을 점진적으로 상향(정식 운용 복귀).
  - 신호 없음/역방향 → 폐기 또는 Hamilton(1989) Markov-switching류 근본 재설계 재논의.
  - 애매함 → 축소 운용 연장.

## 신뢰도 판단 기준선 (2026-07-16 조사)

TAA 운영을 신뢰할 만한 최소 통계적 기준을 문헌 기준으로 정리 — 출처: López de Prado류 backtest 검증 연구, VIX 레짐 오탐율 연구.

| 기준 | 요구치 | 우리 현재(2026-07-16) | 도달까지 |
|---|---|---|---|
| 통계적 추론 시작 바닥 | 30건 | `market_indicators_history.csv` 24~25행 | 약 5~6영업일 (단, "추론 시작 가능"이지 "신뢰 가능"은 아님) |
| 신뢰할 만한 성능지표 | 100건 이상 | 동일 | 약 3~4개월 (매일 누적 가정) |
| 기관급 신뢰도 | 200~500건 & 2~3번의 완전한 시장사이클(약 10~20년) | 동일 | 수년 단위 — 현재 접근(라이브 로그만 쌓기)으로는 비현실적으로 오래 걸림 |
| 단순 임계값 규칙 오탐율(참고) | 확인필터 없음 ≈30%, 확인필터 있음 <20%, HMM/ML <15% | 우리 시스템 실측 오탐율 미측정(계측 시작 단계) | — |
| 다중검정 보정 유의성 기준 | t-stat > 3.0 (Harvey-Liu-Zhu, 2.0은 너무 관대) | 나침반은 지표 8개×임계값 다수 = 자유도 15개 이상, 검정 안 됨 | — |

**시사점**: 지금 로드맵의 4단계("6개월~1년 후 실측")는 이 기준에서 "최소 추론 가능" 수준에 겨우 도달하는 시점이지 "기관급 신뢰도"에는 크게 못 미침. 라이브 로그 축적만으로는 기관급 도달까지 수년이 걸리므로, 아래 "검증 방법 후보"의 외부 장기데이터 백테스트를 병행하는 게 훨씬 빠른 경로.

## 검증 방법 후보 (백테스트 및 대안, 2026-07-16 조사)

| 방법 | 개념 | 장점 | 단점/주의 |
|---|---|---|---|
| A. 라이브 로그 축적 (현재 진행 중, 0단계) | tilt 축소 후 매일 판정 기록 | 진짜 미래 데이터라 과최적화 불가능(가장 신뢰 가능) | 기관급 표본까지 수년 소요 — 가장 느림 |
| B. 외부 장기 과거데이터 백테스트 | KOSPI/VIX/S&P500/환율/유가/국채 등 10~20년치 공개 이력 데이터에 동일 규칙을 소급 적용 | **실행 완료**(2026-07-16) — excess DSR 비유의·MDD 개선만. RESULT 참고 | hindsight bias·그룹 프록시 한계 — C·D·라이브 A로 보완 |
| C. Walk-forward / out-of-sample 분할 | 과거데이터를 훈련구간·검증구간으로 나눠, 훈련구간 밖에서도 성과가 유지되는지 확인 | B의 hindsight bias 위험을 줄이는 표준 방법 | 우리 임계값은 애초에 "훈련"된 적이 없어(사람이 손으로 정함) 어느 구간을 훈련/검증으로 나눌지 설계가 필요 |
| D. PBO/Deflated Sharpe (Bailey & López de Prado) | 다중검정 보정 통계기법 — 백테스트 결과가 과최적화 노이즈인지 통계적으로 검정 | 자유도 15개+ 시스템의 "우연히 좋아 보임" 위험을 정량 검증 가능 | 구현 난이도 있음, 통계 전문성 필요 |
| E. 타 시장 교차검증 | 동일 규칙 구조(임계값은 각 시장에 맞게 재조정)를 미국·일본 등 데이터 긴 시장에 적용해 일관된 효과가 있는지 확인 | 한국 특유 데이터 부족 문제를 우회 | "같은 효과가 났다"고 "한국에서도 통한다"는 보장은 아님 — 참고용 |

## 참고 문헌 (설계 참고용, 2026-07-16 조사)

- Hamilton (1989), *Econometrica* 57 — Markov regime-switching 원조.
- Bry & Boschan (1971) — NBER 스타일 turning-point dating, 최소지속기간·국면교대 제약.
- Merrill Lynch Investment Clock (2004) — 성장×인플레 사분면, 현재 나침반 구조의 원형. 실증 사례 있으나 "경계 모호·안정구간 약화·외부충격기 실패" 비판도 병존.
- Ang & Bekaert (2002), *Review of Financial Studies* 15 — 레짐 반영 국제 자산배분 최적화.
- Chow/Jacquier/Kritzman/Lowry (1999), Kritzman & Li (2010) — Financial Turbulence Index(마할라노비스 거리).
- Estrella & Mishkin (1998), *Review of Economics and Statistics* — 장단기 금리차 프로빗 리세션 모델. **미국 전용 계수 — 한국 재추정 없이 그대로 이식 금지.**
- OECD Composite Leading Indicator 방법론 — 자체 문서에서 "4~8개월 탐지 지연" 인정, 참고만.
- Bailey, Borwein, López de Prado & Zhu — "The Probability of Backtest Overfitting" / Bailey & López de Prado — "The Deflated Sharpe Ratio" — 백테스트 과최적화 검정 통계기법.
- Harvey, Liu & Zhu (2016), *Review of Financial Studies* 29 — 다중검정 보정, t-stat 유의성 기준 2.0→3.0 상향 논거.

## 절대 금지 (전 단계 공통)

- `src/alpha/`(kr_alpha 코어), `take_profit_thesis.py`, `exit_target_worksheet.py` 및 관련 UI — 이 로드맵 범위 아님.
- `score_growth`/`score_inflation`/`score_liquidity`/`score_risk_appetite`의 가중치·계수 자체를 이 로드맵 중간에 임의로 바꾸지 않음(4단계 실측 전까지는 "영향력 축소"만, "판정 로직 재계산 방식 변경"은 1단계 히스테리시스 이외엔 금지).
- 각 단계는 이전 단계 검증 완료 전 다음 단계로 넘어가지 않음.

## 최근 갱신
- 2026-07-16: **방법 B 백테스트 원장 검증 완료.** `replay.py`(PIT lag 재확인: index 500=2017-11-07, 직전 기록 2017-11-06 일치, 미래유출 없음) · `stats.py`(Bailey & López de Prado DSR/PSR 공식 그대로 구현 확인, 조작 없음) · `performance.py`(가중치 1일 lag 후 수익률 적용 — 룩어헤드 없음) 코드 직접 대조, `meta.json` 수치가 `report.md`와 정확히 일치. **이 결과가 4단계의 최종 결론은 아님** — 표본이 국면 사이클 관점에서는 여전히 적고(11.5년), kr_alpha=KOSPI 근사 등 group-proxy 한계가 있어 "TAA가 무용하다"는 증명도 "유용하다"는 증명도 아님. 다음 논의에서 kr_alpha 존폐 결정과 함께 종합.
- 2026-07-16: 방법 B 백테스트 **실행 완료** — [`ECONOMIC_COMPASS_METHOD_B_RESULT.md`](ECONOMIC_COMPASS_METHOD_B_RESULT.md). 판정 시작 2015-10-23~2026-07-15. excess ann −0.26% · **DSR(excess)=0.006(비유의)**. MDD/Vol는 TAA 소폭 우수. 운영 임계값 미변경. korea_10y=`IRLTLT01KRM156N`.
- 2026-07-16: `ECONOMIC_COMPASS_METHOD_B_BACKTEST_SPEC.md` 작성 — 기존 함수 재사용·DSR/PBO 필수. Cursor 구현 완료.
- 2026-07-16: 데이터 가용성 확인 **완료** — [`ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_RESULT.md`](ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_RESULT.md). FRED·Yahoo·KOSPI 셋 다 가능.
- 2026-07-16: `ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_SPEC.md` 작성 — 방법 B 착수 전 데이터 가용성 확인 요청(3항목, 코드 변경 없이 확인만).
- 2026-07-16: "신뢰도 판단 기준선"·"검증 방법 후보" 섹션 추가 — TAA 신뢰 기준(30/100/200~500건+2~3사이클)과 우리 현재 표본(24~25행) 대조, 라이브 로그만으로는 기관급까지 수년 소요됨을 명시. 백테스트를 포함한 5가지 검증 방법(A~E) 비교 기록 — 다음 논의 시 이 표에서 이어가면 됨.
- 2026-07-16: Cursor 게이트 재확인 — `market_indicators_history` **25행/60행** → WAIT. `ECONOMIC_COMPASS_PHASE_2_GATE_CHECK.md` 기록. §2 미착수. 최근 구간은 영업일 누적 가능(`market_indicators_refresh`); 60행까지 잔여 ≈35영업일(매일 실행 가정).
- 2026-07-16: 2단계 착수 전제 직접 확인 — **미충족**. `data/market_indicators_history.csv` 당시 24행(필요 60~120행), `data/prices_history.csv`는 날짜별 종목 커버리지가 불규칙해 부적합. 스펙(`ECONOMIC_COMPASS_PHASE_2_SPEC.md`)은 "지금 구현" 대신 "60행 도달 시 §2 진행" 게이트로 설계.
- 2026-07-16: 원장 검증 완료, 0·1단계 **완료**로 갱신. 코드 직접 대조 결과: `portfolio_builder.py`(tilt_scale 적용·raw/scaled 분리), `hysteresis.py`(confirm_runs·CRISIS 비대칭), `judgment_log.py`, `compass_rules.yaml`(`tilt_governance`/`hysteresis` 키) 전부 스펙대로 구현. `compass_judgment_log.jsonl`·`target_asset_allocation.csv`·`compass_report.md` 3곳의 kr_alpha 수치가 raw×0.4=scaled로 정확히 일치. 단위테스트 6건 로직 직접 추적 확인. **캐비엇**: 유일한 실데이터 로그 1건이 수동 override 활성 케이스(override_active=true, CAUTION)라 tilt 축소는 실증됐지만 히스테리시스 자동판정 경로는 아직 라이브에서 관찰 안 됨(override 없는 날 로그가 쌓이면 자연히 확인됨 — 막는 이슈 아님). `python -m src.main` exit 0은 선택 항목으로 미실행.
- 2026-07-16: Cursor 구현 — 0·1단계 코드/테스트/RESULT 작성, 상태 검증중 (원장 라이브 확인 대기).
- 2026-07-16: 로드맵 문서 최초 작성 (0~4단계 정의, 참고문헌 기록).
