# AI 검증 리포트

- 생성일시: `2026-07-17T14:38:09`
- 시스템 상태: **가동** (go_live=2026-07-17)
- 대시보드 as_of: `2026-07-17`

## 데이터 as_of

- 펀더멘털 (PyKRX/DART): `2026-07-16` — `data/fundamentals.csv`
- 섹터 매핑 (KRX): `2026-07-17` — `data/krx_sector_mapping.csv`
- 현재가 (PyKRX 종가): `2026-07-16` — `data/prices.csv`
- CECS (수동 CSV): `2026-07-16` — `data/cecs_manual_scoring_template.csv`
- T2 / 논지훼손 (수동 입력): `2026-07-17` — `data/alpha_system_journal.jsonl`
- 벤치마크 KOSPI 수익률 (PyKRX): `2026-07-16` — `data/market_indicators.csv`
- KOSPI 시장 PBR 10년 (T3 월간 판정): `2026-06-30` — `data/kospi_market_pbr_history.csv`
- 알파 팩터 스코어 (quant snapshot): `2026-07-17` — `alpha_portfolio/data/output/alpha_scores.csv`
- 정량 스냅샷 provenance: `2026-07-17` — `data/alpha_quant_snapshot_provenance.json`
- 주간 정성 AI 제안 (미승인): `—` — `data/weekly_qual_suggestions.json`

---

## 사용 안내

> AI 답변은 참고용. 출처 원문을 직접 확인한 후에만 이벤트 입력을 진행하세요.

## 1. 검증 질문 (시스템 관측 불가 사실)

### a. T2 제도 이벤트 (각 1건)

#### 상법 시행령·시행규칙 확정 (`commercial_code_enforcement_decrees`)

- **질문:** 상법 관련 시행령·시행규칙이 '확정'되었는가?
- **확정 인정 기준:** 확정 인정 기준 = 관보 게재. 입법예고·보도만으로는 미확정.
- **시스템 기록 상태:** 미기록 (수동 입력 대기)

#### MSCI DM 지수 편입 확정 (`msci_dm_index_inclusion_confirmed`)

- **질문:** 한국(또는 해당 시장)의 MSCI DM 지수 편입이 '확정' 발표되었는가?
- **확정 인정 기준:** 확정 인정 기준 = MSCI 공식 편입 발표. 워치리스트 등재는 발화 아님(제외).
- **시스템 기록 상태:** 미기록 (수동 입력 대기)

#### IFRS18 국내 도입 일정 확정 (`ifrs18_domestic_adoption_schedule_confirmed`)

- **질문:** IFRS18 국내 도입 일정이 '확정'되었는가?
- **확정 인정 기준:** 확정 인정 기준 = 금융위원회 또는 한국회계기준원의 확정 고시. 검토·의견수렴만으로는 미확정.
- **시스템 기록 상태:** 미기록 (수동 입력 대기)

### b. 논지 훼손 징후

- **질문:** 논지 훼손 징후가 있는가? 특히 상법개정(주주환원·지배구조 관련)의 후퇴·유예 움직임이 관측되는가?
- **참고:** 시스템이 자동 관측하지 않음. 1차 출처 기준으로만 답할 것.

### c. 보유 종목 주주환원 정책 변경 공시

- **질문:** 가동 후 보유 종목별로 주주환원 정책 변경 공시가 있었는가? (배당·자사주·정관 등)
- **참고:** 가동(PRE_LAUNCH 해제) 이후에만 해당. 종목 목록은 아래 보유 티커를 사용.

- **보유 kr_alpha 종목:**
  - (보유 없음)


## 2. AI 답변 규칙

1. 모든 답변에 1차 출처(관보·공시·공식 발표) URL을 반드시 포함할 것.
2. 확인 불가 시 '확인 불가'로 답할 것 — 추정·추론 금지.
3. 뉴스 기사만 있고 1차 출처가 없으면 '미확정 보도 단계'로 구분할 것.

## 3. 답변 작성란 (AI 또는 운용자)

_아래에 질문별로 답변·1차 출처 URL을 기입하세요._

```
(답변)
```

