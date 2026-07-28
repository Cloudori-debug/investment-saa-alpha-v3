# CECS 산출 프로세스 — 공수 비교·재해석 규칙 (구현 대기)

> 작성: 2026-07-16  
> 상태: **보고만** — `fetch_cecs_inputs` 구현은 별도 지시 후 진행

---

## 1. 자동화 vs 수동 입력 — 공수 비교

### 1.1 자동화 (`fetch_cecs_inputs.py`, DART OpenAPI)

| 항목 | 내용 |
|------|------|
| **입력** | DART API 키, 종목 corp_code 매핑, 공시 유형 필터 |
| **산출 3축** | execution_continuity · pension_flow_score · investment_purpose_flag |
| **개발 범위** | corp_code 캐시 · 분기별 환원 이벤트 파서 · 대량보유 보고서 시계열 · 투자목적 텍스트 분류 · `StockCatalystProfile` CSV/JSON 출력 |
| **추정 공수** | **5~8 인일** (1인 기준 1~2주) — 파서·엣지케이스·회귀 테스트 포함 |
| **운영 공수** | 분기마다 **배치 1회** (수 분) + API 장애 시 수동 fallback |
| **장점** | gate_pass 159+ 종목 확장 가능, 상관 리포트·재채점 자동화 |
| **리스크** | 공시 형식 변경, 연기금 미보유 소형주 중립 고착, 금융사 환원 공시 표현 차이 |

### 1.2 수동 입력 템플릿

| 항목 | 내용 |
|------|------|
| **입력** | 종목별 DART 열람 → 스프레드시트/Streamlit (`tier_allocation_app.py`) |
| **추정 공수** | **종목당 15~30분** (숙련 시) · 코어 20종 ≈ **1인일** · gate_pass 전수 ≈ **40~80인시** |
| **운영 공수** | **분기마다 전 종목 재검토** 시 동일 규모 반복 |
| **장점** | 즉시 시작 가능, 파서 리스크 없음, 소수 코어 포트에 적합 |
| **리스크** | 확장 불가, 상관 리포트(≥20종) 병목 지속, 기록 일관성 |

### 1.3 권장 경로 (투자 판단 입력)

| 단계 | 권장 |
|------|------|
| **지금 (상관 리포트 전)** | 코어·후보 **20~30종 수동** CECS + 팩터 CSV 병합 → 상관 OK |
| **B안 본격 운용** | `fetch_cecs_inputs` **자동화 착수** (수동 템플릿은 override·감사용 유지) |

---

## 2. 비금융 적용 — 재해석 규칙 (확정안)

CECS 3축은 금융 규제 지표(CET1 등)가 아닌 **공시·수급 서사**. B안에서는 아래를 **동일 척도**로 적용한다.

### 2.1 execution_continuity (가중 0.40)

**정의:** 최근 **4개 분기 연속** 「주주환원 집행」이 공시·재무제표 주석·배당/자사주 공시로 확인되는지.

| 환원 유형 | 인정 조건 | 비금융 | 금융(은행·보험) |
|-----------|-----------|--------|-----------------|
| **현금배당** | 배당 결의·지급 공시 | ✅ | ✅ (배당 위주) |
| **자사주 매입** | 매입 결의·체결 공시 | ✅ | ✅ (제한적이어도 인정) |
| **자사주 소각** | 소각 공시 | ✅ | ✅ |
| **분기 「없음」** | 해당 분기 환원 이벤트 0건 | ❌ 연속성 끊김 | 동일 |

**동일 척도 원칙:** 은행 **배당 1회**와 지주 **자사주 소각 1회**를 다른 점수로 두지 않음 — **「분기당 환원 이벤트 1건 이상」** 이면 그 분기 충족.  
**단,** 한 분기에 배당+매입 동시 있어도 **1분기=1충족** (중복 가산 없음).

**점수:** 4/4 연속 → 1.0 · 3/4 → 0.75 · 2/4 → 0.5 · 1/4 → 0.25 · 0/4 → 0.0

### 2.2 pension_flow_score (가중 0.30)

**정의:** 국민연금 등 **연기금** 대량보유 지분율의 **분기 추세** (증가=가점, 감소=감점, 미보유=중립).

| 상황 | 점수 |
|------|------|
| 연기금 보유 + 2분기 이상 지분 증가 | 0.7~1.0 |
| 보유 + 보합(±0.1%p) | 0.5 |
| 보유 + 지분 감소 | 0.2~0.4 |
| **연기금 미보유** (보고서 없음) | **0.5 (중립)** — 제외 아님 |

비금융·금융 **동일 규칙**. 소형주 중립 고착은 **팩터 한계**로 문서화 (상대순위에서 CECS pension 축 가중 하향 검토는 상관 리포트 후).

### 2.3 investment_purpose_flag (가중 0.30)

**정의:** 대량보유 보고서 「투자목적」 분류.

| DART 표기 | 점수 |
|-----------|------|
| 일반투자 / 단순투자 | 1.0 (기본) |
| 경영참여·지배목적 명시 | 0.3 (감점) |
| 보고 없음 | 0.5 (중립) |

금융지주 vs 운영사 **구분 없음** — 보고서 텍스트만 본다.

### 2.4 policy_dependency_flag (감점 0.15, 별도)

정책·테마 의존(상법 개정 기대 등) **정성 플래그** — 자동화 어려움 → **수동만** (자동 0.5 기본값 허용).

---

## 3. 구현 대기 체크리스트

- [x] 경로 선택: **수동 20~30종 선행** (자동화 상관 리포트 이후) — [`CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md`](CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md)
- [x] 수동 템플릿 — [`data/cecs_manual_scoring_template.csv`](../data/cecs_manual_scoring_template.csv) + [`CECS_MANUAL_SCORING_TEMPLATE.md`](CECS_MANUAL_SCORING_TEMPLATE.md)
- [x] shortlist **30종 승인** — [`CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md`](CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md)
- [ ] `fetch_cecs_inputs.py` 스펙 동결 (YAML화)
- [ ] `alpha_system` `CatalystInputs` 자동 주입 파이프라인
- [ ] T2 `event_candidate_sources`와 중복 없이 연동

---

*관련: [`ALPHA_SYSTEM_CECS_T2_OVERLAP_REPORT.md`](ALPHA_SYSTEM_CECS_T2_OVERLAP_REPORT.md) · [`alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md`](../alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md)*
