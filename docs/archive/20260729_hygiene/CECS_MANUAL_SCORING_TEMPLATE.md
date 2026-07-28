# CECS 수동 채점 템플릿 가이드

> 템플릿 파일: [`data/cecs_manual_scoring_template.csv`](../data/cecs_manual_scoring_template.csv) (확정 30종, 2026-07-16)  
> 확정 shortlist: [`data/cecs_manual_scoring_candidates.csv`](../data/cecs_manual_scoring_candidates.csv)  
> 재해석 규칙 원본: [`ALPHA_CECS_PROCESS_OPTIONS.md`](ALPHA_CECS_PROCESS_OPTIONS.md)  
> 선정 기준·승인: [`CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md`](CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md)

---

## 1. CSV 컬럼

| 컬럼 | 필수 | 설명 |
|------|:----:|------|
| `ticker` | ✅ | 6자리 |
| `name` | ✅ | 종목명 |
| `as_of` | ✅ | 채점 기준일 (동일 스냅샷) |
| `sector` | | KRX 업종 (참고) |
| `is_held` | | 확정 shortlist 보유 여부 |
| `rank` | | 확정 순위 1~30 |
| `execution_continuity` | ✅ | 0.0~1.0 |
| `execution_rationale` | ✅ | **근거 텍스트** (DART 링크·분기·공시명) |
| `pension_flow_score` | ✅ | 0.0~1.0 |
| `pension_rationale` | ✅ | **근거 텍스트** |
| `investment_purpose_flag` | ✅ | 0.0~1.0 |
| `investment_purpose_rationale` | ✅ | **근거 텍스트** |
| `policy_dependency_flag` | | 0.0~1.0 (정성, 기본 0.5) |
| `policy_dependency_rationale` | | 정책·테마 의존 근거 |
| `cecs_computed` | | 자동 계산 (입력 후 스크립트) |
| `scored_by` | ✅ | 채점자 |
| `scored_at` | ✅ | ISO 날짜 |
| `status` | ✅ | `draft` \| `final` |
| `notes` | | 자유 메모 |

**`rationale` 공란 행은 `final` 불가** — 감사 추적용.

---

## 2. 채점 가이드 — execution_continuity (0.40)

**질문:** 최근 4개 분기 연속 「주주환원 이벤트」가 있었는가?

| 환원 유형 | 인정 |
|-----------|------|
| 현금배당 결의·지급 | ✅ |
| 자사주 매입 결의·체결 | ✅ |
| 자사주 소각 | ✅ |

**동일 척도:** 은행 배당 = 지주 자사주 소각 — **분기당 이벤트 1건 이상**이면 그 분기 충족.  
동일 분기 복수 이벤트도 **1분기=1충족** (중복 가산 없음).

| 연속 분기 충족 | 점수 |
|----------------|-----:|
| 4/4 | 1.00 |
| 3/4 | 0.75 |
| 2/4 | 0.50 |
| 1/4 | 0.25 |
| 0/4 | 0.00 |

**rationale 예시:**  
`2025Q3~2026Q2 배당 4회 연속 (DART 정기보고서 배당이력, 2026-07-16 확인)`

---

## 3. 채점 가이드 — pension_flow_score (0.30)

**질문:** 국민연금 등 연기금 지분율 추세?

| 상황 | 점수 |
|------|-----:|
| 보유 + 2분기 이상 지분 증가 | 0.70~1.00 |
| 보유 + 보합 (±0.1%p) | 0.50 |
| 보유 + 지분 감소 | 0.20~0.40 |
| **연기금 미보유** (보고 없음) | **0.50 (중립)** |

비금융·금융 **동일**. 미보유를 0으로 두지 말 것.

**rationale 예시:**  
`국민연금 2025Q4 5.2% → 2026Q1 5.4% (대량보유상황보고서)`

---

## 4. 채점 가이드 — investment_purpose_flag (0.30)

**질문:** 대량보유 보고서 「투자목적」?

| DART 표기 | 점수 |
|-----------|-----:|
| 일반투자 / 단순투자 | 1.00 |
| 경영참여·지배목적 명시 | 0.30 |
| 보고 없음 | 0.50 |

금융지주 vs 운영사 구분 없음 — **보고서 텍스트만** 본다.

**rationale 예시:**  
`2026Q1 대량보유보고 투자목적=일반투자`

---

## 5. policy_dependency_flag (감점 0.15)

상법 개정·IFRS18 등 **정책 기대 의존** 정성 플래그. 자동화 어려움 — 수동만.

| 수준 | 점수 |
|------|-----:|
| 낮음 (실질 환원·실적 중심) | 0.2~0.4 |
| 중립 | 0.5 |
| 높음 (테마·입법 편승) | 0.7~1.0 |

---

## 6. CECS 합성 (참고)

`alpha_system` 가중:

```
cecs = 0.40×execution + 0.30×pension + 0.30×purpose
       − 0.15×policy_dependency   (엔진 clamp 적용)
```

→ 0~100 스케일 `cecs`는 팩터 CSV 병합 시 변환.

---

## 7. 작성 순서

1. 확정 shortlist 30종 — [`data/cecs_manual_scoring_candidates.csv`](../data/cecs_manual_scoring_candidates.csv) (승인 2026-07-16)  
2. 템플릿에서 종목별 DART 확인 → 3축 점수 + **rationale 3건 필수**  
3. `status=final` → 팩터 CSV 생성 시 병합  
4. 상관 리포트 실행 (`sector`·`sector_peer_fallback` 컬럼 포함 권장)

---

*자동화(`fetch_cecs_inputs`)는 상관 리포트 OK 이후 착수.*
