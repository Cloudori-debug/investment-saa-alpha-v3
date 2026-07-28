# 유니버스 B안 — 섹터 메타 정비 RESULT

> 작성: 2026-07-16  
> 전제: `universe.boundary_mode = shareholder_return_broad` (KOSPI + Gate, 금융 전용 필터 없음)

---

## 1. boundary_mode·벤치마크 (항목 1·4)

| 항목 | 확정값 | 위치 |
|------|--------|------|
| `boundary_mode` | `shareholder_return_broad` | `alpha_system/config/alpha_system.yaml` |
| 발굴 범위 | KOSPI 보통주 + `data/universe_filter.yaml` Gate | 동일 + `universe.include_markets: [KOSPI]` |
| 금융 전용 필터 | **`financial_only_filter: false`** (명시) | 동일 |
| 벤치마크 | **`benchmark: KOSPI`** (단일 문자열) | 동일 |
| 미연동 참고 | `alpha_portfolio/config/universe_gate.yaml` primary=KOSPI200, secondary=KOSPI | **alpha_system과 코드 연동 없음** — 문서만 |

---

## 2. sector unknown 150/159 — 원인 진단 (항목 2a)

### 2.1 현상

과거 `alpha_portfolio/data/input/screening_universe.csv` 기준 **gate_pass 159종 중 sector=unknown 150종 (94%)**.

### 2.2 근본 원인 (매핑 소스 부재 + 파이프라인 미연결)

| 단계 | 원인 | 근거 |
|------|------|------|
| 유니버스 수집 | PyKRX `fetch_universe`가 **`sector: ""` 고정** | `alpha_portfolio/src/collect/pykrx_collector.py` L59 |
| liquid stub | universe 메타의 빈 sector → **`unknown` 기본값** | `liquid_fundamentals.py` (수정 전) |
| 스크리너 merge | `build_merged_frame`이 **fundamentals.sector만** 사용, KRX 매핑 미조인 | `screener.py` |
| 본체 universe | `data/universe.csv` **sector/industry 대부분 공란** | 진단 스크립트·CSV 샘플 |
| 매핑 테이블 | `data/krx_sector_mapping.csv`는 **이미 존재**(PyKRX 2,690행) | 파이프라인이 **참조하지 않음**이 문제 |

**판정:** 파싱 실패가 아니라 **「수집 단계에서 sector 미채움 + 매핑 테이블 미연결」** 이 1차 원인. GICS 부재 이슈 아님.

### 2.3 조치 (코드)

- `alpha_portfolio/src/sector_enrich.py` — `data/krx_sector_mapping*.csv` 조인
- `pipeline.run_pipeline` — merge 직후 `enrich_sectors()` 호출
- `liquid_fundamentals` — stub 생성 시 `resolve_ticker_sector()` 사용

---

## 3. 섹터 분류 소스 확정 (항목 2b)

| 항목 | 결정 |
|------|------|
| **1차 소스** | **KRX 공식 업종** — PyKRX `get_market_sector_classifications` |
| GICS | **사용 안 함** (`data/krx_sector_taxonomy.yaml` `gics_used: false`) |
| 스코어링 peer 키 | **`krx_sector`(업종명)** — `02_스코어링_설계` 섹터 백분위 |
| `sector_group` | 26개 조분류 — 캡·리포트용, percentile 축 아님 |

### 데이터 파일

| 파일 | 역할 |
|------|------|
| `data/krx_sector_mapping.csv` | KRX 공식 자동 갱신본 |
| `data/krx_sector_mapping_manual.csv` | 수동 override (우선순위 최상) |
| `data/krx_sector_taxonomy.yaml` | KRX 업종명 → `sector_group` |

**갱신 절차:** [`docs/DATA_SECTOR_MAPPING_REFRESH.md`](DATA_SECTOR_MAPPING_REFRESH.md)

---

## 4. gate_pass 섹터 커버리지 (항목 2c)

`data/krx_sector_mapping.csv` 적용 후 (`resolve_sector` 기준):

| 지표 | 값 | 목표 |
|------|-----|------|
| gate_pass 종목 | **159** | — |
| unknown | **0** (0%) | **<5%** ✅ |
| 조치 | `012510` 더존비즈온 → `krx_sector_mapping_manual.csv` (IT 서비스) | 2026-07-16 반영 |

상세 JSON: `data/sector_coverage_gate_pass.json`

### 업종 분포 (상위 10)

| KRX 업종 | 종목 수 |
|----------|--------:|
| 전기·전자 | 30 |
| 기타금융 | 15 |
| 기계·장비 | 15 |
| 운송장비·부품 | 10 |
| 제약 | 10 |
| 화학 | 9 |
| 일반서비스 | 9 |
| IT 서비스 | 7 |
| 유통 | 6 |
| 은행/금융지주* | 4 |

\* 수동 fundamentals에 남아 있는 **비-KRX 라벨** 일부 존재 — 신규 수집분은 KRX 업종명으로 통일됨. 레거시 수동 행은 verified=manual 이면 enrich가 **덮어쓰지 않음** (`overwrite=False`).

---

## 5. 표본 <5 → 시장 fallback 섹터 (항목 2d)

`factors._sector_series`: 동일 sector 표본 **<5**이면 **시장 전체** percentile fallback.

gate_pass 159종 기준 **표본<5 업종 32개** (전부 fallback 대상):

건설(2), 보험(2), 통신(2), 음식료·담배(2), 운송·창고(2), 은행(2), 금속(4), 은행/금융지주(4), 증권/금융지주(4), … 및 표본 1종 업종 24개 — 전체 목록은 `data/sector_coverage_gate_pass.json` → `sectors_sample_lt_5`.

**시사점:** gate_pass 풀(159)에서는 **다수 업종이 KRX 정식 라벨 기준으로도 표본 부족**. 이는 B안 확대 시 자연 해소되나, 초기 상관·스코어링에서는 **시장 fallback 비율이 높음** — 팩터 CSV 20종 이상 확보 시에도 peer 품질 모니터 필요.

---

## 6. 후속

1. `012510` 수동 매핑 1건 또는 `refresh_krx_sector_mapping.py` 재실행  
2. CECS 산출 경로 확정 — [`ALPHA_CECS_PROCESS_OPTIONS.md`](ALPHA_CECS_PROCESS_OPTIONS.md) (구현 대기)  
3. 팩터 CSV → 상관 리포트

---

*관련: [`ALPHA_UNIVERSE_BOUNDARY_FACT_CHECK.md`](ALPHA_UNIVERSE_BOUNDARY_FACT_CHECK.md)*
