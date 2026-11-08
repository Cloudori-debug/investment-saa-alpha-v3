# 듀얼 모멘텀 (GEM) — 연구 카드

> **상태:** active  
> **프로그램 매핑:** 전략 › 듀얼모멘텀 · 월 GEM  
> **갱신:** 2026-11-08 · 정석 근사(EAFE·상대→절대)
## 1. 한 줄

상대모멘텀으로 강세 주식권역을 고르고, **절대모멘텀이 깨지면 채권/안전자산**으로 간다.  
**정식 GEM 자산군 ≠ 코스피200** · 한국 지수를 넣으면 변형이다.

## 2. 위치

- UI: 듀얼 시그널 · 월말 전량 교체 Review
- 집행: **앱 밖** · Soft·정적 본체와 합산 금지
- S&P 200일 Soft와 병행 관측 (덮어쓰기 없음)
- 코스피 Soft 신규 게이트([`MID_KOSPI_ENTRY_GATE_SPEC.md`](../../MID_KOSPI_ENTRY_GATE_SPEC.md))는 **변형에 코스피200을 둘 때의 허가 Soft** 후보 · GEM 상대모멘텀 규칙 대체 아님

## 3. 문헌

| 문헌 | ID | 요지 |
|------|-----|------|
| Dual Momentum Investing (2014) Ch.8 GEM | ANTONACCI_DM_BOOK | 미 vs 비미 주식 · 절대깨짐→미종합채 · 월·대개 12M · 전량 1종 |
| Risk Premia Harvesting Through Dual Momentum | ANTONACCI_DM_SSRN | 상대+절대 · 절대가 변동·낙폭 완화에 더 기여 · [SSRN 2042750](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750) |
| Absolute Momentum | ANTONACCI_ABS_SSRN | 시계열(절대) 모멘텀 단독·오버레이 · [SSRN 2244633](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2244633) |
| Dual Momentum for non-US investors | ANTONACCI_NONUS | 비미 투자자도 **동일 USD 축 지수**(S&P·ACWI ex-US·US Agg) 권고 경향 · [Optimal Momentum](https://www.optimalmomentum.com/dual-momentum-for-non-us-investors/) |
| Time Series Momentum (Moskowitz–Ooi–Pedersen 2012) | TSMOM_2012 | 선물 다자산 절대모멘텀 · GEM 레시피와 별개 · 국가 주가지수 포함 가능 |
| Regime → cash | ANG_BEKAERT_2003 | 베어·고변동 시 현금 가치 |
| Seasonality vs GEM | OPTIMAL_MOM_SEASON | 계절 규칙을 GEM에 얹는 건 대체로 비추 |

## 3b. 자산군 대조

### 정식 GEM (책·실무 표준)

| 역할 | 자산 | 대표 프록시 | 비고 |
|------|------|-------------|------|
| 공격① | 미국 주식 | SPY / VOO (S&P 500) | |
| 공격② | 미국 제외 세계 주식 | VXUS / VEU (ACWI ex-US) · 백테스트에 EFA(EAFE)도 흔함 | EM은 보통 **별도 슬리브 추가 안 함**(ACWI 안에만) |
| 방어 | 미국 종합채 | AGG / BND | 주식·채 동락 구간 약점 |
| 허들 | T-bill | BIL | **보유하지 않음** · 절대모멘텀 기준만 |

월말: 상대(미 vs 비미) → 승자(또는 미국) 12M이 T-bill을 이기면 주식 100% · 아니면 종합채 100%.

### 우리 앱 근사 (`household_static_alloc.yaml` · `dual_momentum`) — **정석 판단**

| 역할 | 티커 | 비고 |
|------|------|------|
| 공격① | `360750` TIGER 미국S&P500 | SPY 근사 |
| 공격② | `195970` PLUS 선진국MSCI(합성 H) | **MSCI EAFE** · EFA 근사 · 미·캐나다 제외 선진 |
| 허들 | `329750` 달러단기 | BIL 근사 |
| 방어 | `437080` 미국종합채권(H) | AGG 근사 |

**월말 규칙(정석 순서):** ① 상대(미 vs EAFE) 승자 → ② 그 승자 12M > 달러단기 ? 예=승자 100% / 아니오=채 100%.

**넣지 않음(정석):** 코스피 Soft · 유로50단독(`195930`) · 배당30(`245350`) · 별도 EM 슬리브(문헌도 GEM에 EM 단독 비권고).  
→ ACWI ex-US 단일 국내 ETF 부재로 EAFE가 **가능한 최선 근사** · Soft/target 불변 · Review-only.  
→ 설계 검증: [`static-all-weather.md`](static-all-weather.md) §11.  
→ 갱신: 2026-11-08 · 유로단독→EAFE · 절대=승자 게이트.

### 코스피200을 넣는 경우 (변형 · 정식 아님)

| 항목 | 내용 |
|------|------|
| 무엇인가 | 공격 유니버스에 **코스피200(예: `069500`/`102110`)** 을 추가한 상대모멘텀 변형 |
| 무엇인가 아닌가 | Antonacci 정식 GEM 3자산군 **아님** · TSMOM 다국가 선물 유니버스와도 동일하지 않음 |
| 쓸 때 | 월 시그널은 여전히 **상대+절대** · 코스피 Soft 신규 게이트는 **허가 Soft**(닫힘/대기 시 코스피200 신규 보류 Review) |
| 하지 않는다 | Soft 개별주·정적/`compass_fit`·Executable과 **합산 집행** · 낙폭만으로 코스피200 강제 편입 · target 자동 |

## 4–5. 결론 · Soft

- **한다:** 월 1회 시그널 Review · 약세면 안전자산 · (변형 시) 코스피200은 게이트 통과 후에만 Review
- **하지 않는다:** Soft 일일 매매와 섞기 · 계절만으로 교체 · 코스피200을 “정식 GEM 자산”으로 표기

## 6. 한계

룩백 12M 민감 · 횡보장 휩쏘 · ETF 추적오차 · 유럽 근사로 인한 ACWI 괴리 · (변형) 미·한 동락 시 상대모멘텀 정보량↓.  
정식 GEM 대비 좁은 다리는 **제약최적의 비용** · Lab CAGR로 공격 유니버스를 키우는 식의 재최적화와 혼동하지 않음.  
고금리 유리 여부는 전체 Lab만으로 단정하지 않음 · 백테스트「국면 슬라이스 Lab」(실질≥1%·연준≥3%·2022~·stage≥4)로 Review.  
미국 발행 ETF 교차검증: 백테스트「미국 ETF GEM 국면 Lab」(SPY·EFA/VXUS·BIL·AGG · Yahoo adjclose · 동일 국면 정의).  
대공황~ 장기: 백테스트「장기 월간 GEM」(Ken French 미국 1926-07~ · Dev ex-US 1990-07~ · 절대모멘텀이 대공황 구간 본체).  
**종합(2026-11-08):** 고금리 우려→듀얼 **본체 승격 기각** · 선택위성만 · 낙폭완화는 절대모멘텀이 기여(대공황 Lab 부분지지) · 상세 [`static-all-weather.md`](static-all-weather.md) §12.
