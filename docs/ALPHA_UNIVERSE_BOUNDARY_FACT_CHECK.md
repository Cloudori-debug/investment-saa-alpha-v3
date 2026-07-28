# 유니버스 경계 결정 전 사실 확인 보고서

> 작성: 2026-07-16  
> 범위: **조사·보고만** (코드 변경 없음)  
> 목적: A/B/C 유니버스 안(금융 중심 vs 주주환원 전반 vs 절충) 결정에 필요한 사실 정리

---

## 요약 판정

| # | 질문 | 핵심 답 |
|---|------|---------|
| 1 | tier_weighting 명세에 유니버스/후보 리스트? | **없음** — CECS·티어링만. 유니버스는 `alpha_portfolio`·`data/universe_filter.yaml` 쪽 |
| 2 | CECS 3하위지표 금융 전제? | **CET1·배당가능이익 등 규제 지표 없음**. 공시·대량보유 기반 — 비금융 적용 가능하나 **해석·데이터 품질 재검토** 필요 항목 있음 |
| 3 | Q/V/SR/R 업종 간 비교? | **섹터 백분위·예외 플래그 구조**. V는 단일 PBR 아님. 금융·지주 **예외 분기 이미 있음** |
| 4 | T3 밴드 이원화? | **(a) 포트 단일 불리언 훅만** — 종목/업종별 산식 **미지원** |
| 5 | 팩터 CSV 데이터 계획? | `alpha_system` 내 **공식 파이프라인 문서 없음**. `alpha_portfolio` 스키마·수집기가 사실상 원천 |
| 6 | 벤치마크 훅? | `alpha_system`은 **단일 문자열 1개** — 복수/합성 **미지원** |

---

## 1. `kospi_alpha_tier_weighting_spec.md` 유니버스·후보 리스트

### 1.1 명세 본문

`C:\Users\clowo\Downloads\kospi_alpha_tier_weighting_spec.md` (저장소 외부 원본) 전체를 검토한 결과:

- **고정 종목 리스트·업종 화이트리스트·블랙리스트 없음**
- 언급되는 것은 **운용 규모 예시**(7종목 기준 티어당 목표 종목 수), **테마 서술**(저PBR·자사주·상법·IFRS18·「하케다카」), **CECS 하위지표·티어 배분**뿐
- 입력은 `StockCatalystProfile` 리스트를 **이미 6팩터 엔진이 산출했다고 가정** — 유니버스 정의는 명세 범위 밖

### 1.2 실제 유니버스가 정의된 위치 (연관 시스템)

| 출처 | 내용 |
|------|------|
| `alpha_portfolio/docs/00_개념정집.md` v0.2 | **발굴 범위: KOSPI 전체** / 성과: KOSPI 200 중심 |
| `alpha_portfolio/config/universe_gate.yaml` | Gate 임계값(시총 3천억·거래대금 10억 등) + 벤치마크 primary KOSPI200 |
| `data/universe_filter.yaml` | KOSPI **보통주**만, 우선주·ETF·REIT·SPAC·거래정지 등 제외, 유동성 프리셋(standard: 시총 5천억·20일 거래대금 15억) |
| `alpha_system/config/alpha_system.yaml` | `universe.boundary_mode`: `financial` \| `shareholder_return_broad` — **[TODO] null**, 필터 로직 미연결 |

### 1.3 샘플 데이터의 업종 분포 (참고 — 고정 후보 아님)

**`alpha_portfolio/data/input/screening_universe.csv`** (Gate 통과, `gate_pass=true`):

| sector | 종목 수 | 비고 |
|--------|--------:|------|
| unknown | 150 | PyKRX 유동성 stub 행 — `sector`·재무 미채움 |
| consumer | 3 | 코웨이, 동원산업, 현대그린푸드(유동성 fail) 등 |
| holding | 2 | 현대GF, SNT홀딩스 |
| insurance | 1 | DB손해보험 |
| materials | 1 | KCC |
| data_service | 1 | NICE평가정보 |
| semiconductor | 1 | SK하이닉스 |
| **합계 gate_pass** | **159** | |

**수동 입력·보유 중심 코어 표본**(unknown 제외, 11종): 금융 1 · 소비 3 · 지주 2 · 소재 1 · 데이터 1 · 반도체 1 — **「금융 전용 리스트」가 아니라 현재 kr_alpha 보유·샘플 혼합**.

**`data/universe.csv`** (본체 KOSPI 마스터, 2,765행): `sector`/`industry` 컬럼 **대부분 공란**. 종목명 키워드 추정(금융·보험·은행·지주 등) **약 83종** — 전체의 ~3%, **공식 금융 유니버스 정의 아님**.

### 1.4 판정

- tier_weighting 명세만으로는 **A/B/C 유니버스를 고를 근거 없음**
- B안(주주환원 전반) 전환 비용은 **스코어링·Gate는 이미 비금융 친화**이나, **CECS 자동화·T3 밴드·섹터 메타데이터**가 병목

---

## 2. CECS 하위 3지표 (execution / pension / purpose) — 정의·금융 전제

> 현재 `alpha_system` 스코어용 CECS는 **5팩터 정리 후** 아래 3개만 가중합  
> (`disclosure_status`·`independent_catalyst_flag`는 T2 후보로 이관, 스코어 제외)

### 2.1 원본 정의 인용 (`kospi_alpha_tier_weighting_spec.md` §2.2)

| 지표 | 명세 설명 | 데이터 소스 |
|------|-----------|-------------|
| **execution_continuity** | 최근 **4개 분기 연속** 소각·환원 실적 존재 여부 | DART 정기공시 |
| **pension_flow_score** | 국민연금 등 연기금 **지분율 변동 추세**(분기 연속성) | DART 대량보유상황보고서 |
| **investment_purpose_flag** | 연기금 투자목적이 일반투자/경영참여인지 (**단순투자 감점**) | DART 대량보유상황보고서 |

가중(현재 `alpha_system/config/scoring.yaml`): execution **0.40** / pension **0.30** / purpose **0.30**  
`policy_dependency_flag` 감점 0.15는 별도(정성·테마 의존도) — **금융 규제 지표 아님**

### 2.2 금융업 전제 지표 여부

| 검색 대상 | 결과 |
|-----------|------|
| CET1, BIS, 자본적정성 | **명세·코드 어디에도 없음** |
| 배당가능이익, 금융감독 배당 규제 | **없음** |
| 은행 전용 밸류에이션 (PBR vs BPS 조정 등) | CECS 범위 **외** — Q/V 쪽 `is_financial` 예외만 존재 |

**판정: CECS 3지표는 「금융 규제」가 아니라 「주주환원·기관 수급·공시」 서사**에 가깝다.

### 2.3 비금융 적용 가능성

| 지표 | 비금융 직접 적용 | 재해석·주의 |
|------|------------------|-------------|
| **execution_continuity** | **가능** — 자사주·배당·소각은 비금융도 DART 동일 계열 | 금융사는 환원 형태(배당 위주·자사주 제한)가 다를 수 있어 **분기 연속 정의를 업종별로 통일**해야 함 |
| **pension_flow_score** | **가능** — 대량보유 보고는 업종 무관 | 연기금 보유가 적은 소형주는 **중립(0.5) 고착** 위험 — 표본 편향 |
| **investment_purpose_flag** | **가능** — 보고서 텍스트 분류 | 파싱 규칙 미확정(명세 §8). **금융지주 vs 운영사** 혼동 주의 |

### 2.4 구현 상태

- `alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md`: **`fetch_cecs_inputs.py` 미구현** — UI 슬라이더·수동 입력 단계
- `alpha_system`: `CatalystInputs` 기본값 0.5 — **자동 산출 파이프라인 없음**

---

## 3. Q / V / SR / R — 입력 정의·업종 간 비교

출처: `alpha_portfolio/docs/02_스코어링_설계.md`, `src/factors.py`, `01_데이터_스키마.md`

### 3.1 공통 정규화

- **percentile_score**: 동일 **sector** 내 백분위 (sector 표본 < 5 → **시장 전체** fallback)
- **linear_score**: 절대 구간 매핑 (ROE, 부채, 배당 등)

### 3.2 팩터별 요약

| 팩터 | 구성 | 금융/지주 예외 |
|------|------|----------------|
| **Q** | ROE linear(5~20%) · OPM **sector %** · 부채 linear(invert) · 이익안정 | `is_financial` → Q3=50, Gate G06 면제 · `is_holding` → 가중 재배분 |
| **V** | PER·PBR **/ sector median** % · EV/EBITDA sector % · FCF yield linear | `is_holding` → PBR 가중 0.55 — **단일 PBR 아님** |
| **SR** | 배당수익률 · 배당성향 · buyback_3y | shareholder.csv 없으면 **50 중립** |
| **R** | 변동성 · 52주 위치 · beta vs KOSPI200 | beta 결측 → 50 |

### 3.3 V(밸류) — 단일 지표 vs 업종 분기

**단일 PBR이 아님.** 기본: PER 35% + PBR 35% + EV/EBITDA 15% + FCF 15%, PER/PBR는 **섹터 중위 대비 비율**의 sector 백분위(저평가=고점).  
지주는 **PBR/NAV 디스카운트 중심**으로 서브가중 변경.

### 3.4 업종 간 비교 가능성 평가

| 관점 | 평가 |
|------|------|
| 동일 sector 내 순위 | **설계 의도** — 비교 가능 |
| 금융 vs 비금융 횡단 | 부채·PER 해석이 달라 **예외 플래그로 완화만** — 완전 동질 비교는 아님 |
| B안(지주·저PBR 확대) | `is_holding` 분기 **이미 있음** — 추가 코드보다 **sector·is_holding 메타 정확도**가 관건 |
| A안(금융만) | 별도 유니버스 필터는 **아직 없음** — Gate만으로는 금융 한정 불가 |

---

## 4. T3 밸류에이션 밴드 config — (a) vs (b)

### 4.1 현재 스키마

`alpha_system/schema.py` — `TrancheConfig.valuation_band: Optional[dict[str, Any]]`  
`alpha_system/config/alpha_system.yaml` — `T3.valuation_band: null` [TODO]

### 4.2 현재 런타임 동작 (`entry/evaluate.py`)

1. config에 `valuation_band` dict가 **없으면** T3 발화 불가  
2. `TriggerSnapshot.valuation_band_touched: Optional[bool]` — **포트폴리오 단일 불리언**  
3. dict 내용(산식·임계) **파싱 없음** — true/false만 소비

### 4.3 판정

| 옵션 | 지원 여부 |
|------|-----------|
| **(a) 포트 전체 단일 산식** | **부분만** — config 자리·불리언 훅만 있고 **산식 엔진 없음** |
| **(b) 종목/업종 이원화**(은행 PBR 밴드 + 지주 NAV 할인 등) | **미지원** |

### 4.4 (b) 지원 시 변경 범위 추정 (구현 안 함)

| 영역 | 작업 |
|------|------|
| config 스키마 | `valuation_band`를 typed 구조로 (예: `scope: portfolio \| sector \| ticker`, `metric`, `lower`, `upper`, `sector_overrides[]`) |
| 평가 입력 | `TriggerSnapshot`에 **종목별** `valuation_band_touched: dict[str, bool]` 또는 산출 모듈 출력 |
| T3 평가 | 밴드 산식 계산기 + 집계 규칙(포트 vs any-name vs all-names) |
| 데이터 | sector·PBR·NAV·금융/지주 플래그 — `fundamentals` 품질 의존 |
| 리포트/테스트 | T3 READY 사유에 metric·threshold 명시 |

**절충안 C(업종별 T3)** 실행 비용: **중~대** — 유니버스 결정과 **독립적으로** T3를 먼저 단일 산식으로 가도 되나, B안과 동시면 (b) 쪽 설계가 사실상 필요.

---

## 5. 팩터 CSV(상관 리포트) — 기존 계획·원천 데이터

### 5.1 `alpha_system` 요건 (`scoring/correlation.py`)

컬럼: `ticker` + **`score_q`, `score_v`, `score_sr`, `score_r`, `cecs`** (5축)  
※ `factor_score_total`은 상관 축에서 제외(내부 blend용). 사용자 요청의 7열 CSV는 **구버전 계약** — 현재 코드는 **5축**.

- 최소 **20종목**, 동일 **as_of** 스냅샷  
- 결측 impute 금지, 미달 시 **SKIPPED** (가짜 상관 없음)

### 5.2 코드·문서 내 「공식 데이터 소스 계획」

| 위치 | 내용 |
|------|------|
| `alpha_system` | **팩터 CSV 생성 파이프라인 문서·CLI 없음** — `run_reports.py`는 리포트만 |
| `alpha_portfolio/docs/01_데이터_스키마.md` | **P0~P2 수집 로드맵** (수동 재무 + PyKRX 가격 → OpenDART) |
| `alpha_portfolio/docs/00_개념정집.md` | P0: 수동 CSV + PyKRX / P1+ DART |
| `05_CECS_TIER_WEIGHTING.md` | CECS DART 자동화 **미구현** |

### 5.3 팩터별 원천 데이터 항목 (목록화)

| 출력 컬럼 | 필요 원천 | 주요 필드·공시 | 현재 저장소 |
|-----------|-----------|----------------|-------------|
| **score_q** | fundamentals + Gate | `roe`/`roe_3y_avg`, `opm`, `debt_ratio`, `is_financial`, `is_holding`, `net_income_y1/y2`, `sector` | `alpha_portfolio` fundamentals 수동 / `data/fundamentals.csv` (스키마 상이) |
| **score_v** | fundamentals + cross-section | `per`, `pbr`, `ev_ebitda`, `fcf_yield`, `sector_per_median`, `sector_pbr_median`, `sector` | 동일 |
| **score_sr** | shareholder (optional) | `dividend_yield`, `payout_ratio`, `buyback_3y` | `shareholder.csv` P0 수동 |
| **score_r** | price_snapshot | `close`, `high_52w`, `low_52w`, `volatility_1y`, `beta_kospi200` | PyKRX / `prices.csv` |
| **cecs** | DART (미자동) | execution·pension·purpose 3축 + `policy_dependency_flag` | **수동·기본값** — 자동 원천 없음 |

**병목:** (1) **동일 as_of로 20+ 종목** Gate 통과 풀 (2) **CECS 자동 입력 없음** (3) 본체 `data/fundamentals.csv`와 `alpha_portfolio` 스키마 **불일치** — 그대로 합치면 재매핑 필요.

### 5.4 현실적 확보 경로 (제안 — 미구현)

1. `alpha_portfolio` 스크리너로 `screening_universe` → `alpha_scores.csv` 생성 (Q/V/SR/R)  
2. CECS는 **수동 CSV 병합** 또는 `fetch_cecs_inputs` 구현 전까지 **상관에서 cecs 제외 별도 실행**은 불가(5축 필수)  
3. `sector` unknown 행(현재 150/159) 제거하려면 **fundamentals.sector·verified** 채우기 선행

---

## 6. 벤치마크 훅 — 단일 vs 복수

### 6.1 `alpha_system`

| 항목 | 내용 |
|------|------|
| config | `benchmark: null` — 단일 `Optional[str]` (`KOSPI` \| `KRX_finance` 등 **문자열 하나**) |
| report | `render_performance_hook` — **한 줄** 표시, null이면 「비교 훅만」 |
| 복수·합성·가중 | **스키마·코드 없음** |

### 6.2 연관(미연결) 설정

- `alpha_portfolio/config/universe_gate.yaml`: `benchmark.primary: KOSPI200`, `secondary: KOSPI` — **alpha_system과 미연동**
- `data/core_saa_reference.yaml`: Core SAA ETF 벤치마크 — **알파 단독 시스템 외부**

### 6.3 판정

- **단일 지수 전제** (문자열 1개 확정 시 비교 가능하도록 **훅만** 존재)  
- 복수 벤치마크(예: 50% KOSPI + 50% 금융)는 **config 확장 + 성과 계산 모듈** 추가 필요

---

## 7. A / B / C 유니버스 안에 대한 시사점 (투자 판단 입력)

| 안 | 사실 기반 시사 |
|----|----------------|
| **A 금융 중심** | tier_weighting 명세에 **리스트 없음**. Q/V는 `is_financial` 예외만 있고 **금융 필터·CECS 은행 해석은 미정의**. **신규 universe 규칙 + sector 메타** 필요 |
| **B 주주환원 전반** | Gate·Q/V/SR이 **이미 비금융·지주 분기 지원**. CECS·T2는 **환원 공시 서사**와 정합. **전환 비용 = CECS/T3 데이터·자동화** 쪽이 큼 |
| **C 절충(T3 업종별)** | T3 **(b) 미지원** — 실행 비용 **중~대**. 유니버스를 B로 가도 T3는 별도 엔지니어링 |

**권장 결정 순서(사실 기반):**  
1) `universe.boundary_mode` 확정 → 2) `sector`/`is_financial`/`is_holding` 마스터 정비 → 3) CECS 입력 경로 → 4) T3 밴드 (단일 vs 이원화) → 5) 벤치마크 1개 확정 → 6) 팩터 CSV로 상관 OK

---

## 8. 참고 파일 인덱스

| 파일 | 용도 |
|------|------|
| `kospi_alpha_tier_weighting_spec.md` (Downloads) | CECS 원본 — 유니버스 없음 |
| `alpha_portfolio/docs/00_개념정집.md` | KOSPI 전체 발굴 |
| `alpha_portfolio/docs/02_스코어링_설계.md` | Q/V/SR/R 정의 |
| `alpha_portfolio/docs/01_데이터_스키마.md` | CSV·수집 로드맵 |
| `data/universe_filter.yaml` | KOSPI 보통주·유동성 |
| `alpha_system/config/alpha_system.yaml` | boundary_mode·T3 TODO |
| `alpha_system/scoring/correlation.py` | 팩터 CSV 요건 |
| `alpha_system/report/__init__.py` | 벤치마크 훅 |

---

*본 보고서는 코드 변경 없이 기존 명세·설정·샘플 데이터를 조사한 결과입니다.*
