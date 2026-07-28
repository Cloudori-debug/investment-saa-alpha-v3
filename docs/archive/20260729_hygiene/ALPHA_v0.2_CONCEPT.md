# Alpha v0.2 — Shadow / Research Engine

> **역할:** 새 알파 철학 검증. **v1.0.2 실행·trade_actions·target 변경 없음.**  
> **기간:** 90~120일 shadow 병렬 운용 후 legacy screener 대체 여부 결정.

---

## 1. 정체성

| 레이어 | 권한 |
|--------|------|
| v1.0.2 execution | **돈을 움직임** |
| v1.1a shadow diagnostic | 왜 막혔는지 기록 |
| **alpha_v0.2 shadow** | 보유·후보 **재분류·연구** |

Alpha는 전체 포트의 **위성 슬리브**다. SAA/TAA/shadow는 건드리지 않는다.

---

## 2. 예산 원칙 (v0.2 권장 — shadow 표시만)

| 항목 | 값 |
|------|-----|
| Alpha target | 10~15% |
| Alpha max | 20~25% |
| 단일종목 기본 | 1~3% |
| Core 단일 max | 5% |
| 예외 max | 8% |
| 섹터 max | 25~30% |

현재 kr_alpha ~40%대이면 shadow는 `alpha_budget_status: OVERWEIGHT`, `new_alpha_buy_allowed: false`를 출력한다.

---

## 3. 파이프라인 순서

```
Universe (kr_alpha 보유·목표 + research pool)
  → Exclusion Gate
  → Quality Gate
  → Value Score
  → Momentum (90/120일 = 3m/6m vs KOSPI200)
  → Catalyst
  → Risk Budget
  → Classifier (Core / Active / Candidate / Watch / Legacy / Exit)
  → Benchmark vs legacy screener
```

**원칙:** Value가 먼저가 아니라 **Exclusion · Quality가 먼저**.  
**Quality fail → 신규매수 금지.** **Momentum fail → 신규매수 금지.**

---

## 4. 점수 (100점)

| 항목 | 비중 |
|------|------|
| Quality | 30 |
| Value | 25 |
| Momentum | 20 |
| Catalyst | 15 |
| Risk Control | 10 |

| 점수 | 분류 |
|------|------|
| ≥80 | Core 후보 |
| 70~79 | Active |
| 60~69 | Candidate |
| 50~59 | Watch |
| <50 | Legacy / Excluded |

---

## 5. Momentum (value trap 방지)

| 조건 | 판단 |
|------|------|
| 90일 RS > KOSPI200 | 긍정 |
| 120일 RS > KOSPI200 | 강한 긍정 |
| 90↑ 120↓ | Candidate |
| 90·120 모두 열위 | 신규매수 금지 |
| 악화 지속 + 보유 | Legacy / Exit |

벤치마크: KODEX 200 (`069500`). 90/120일 = `return_3m` / `return_6m` 상대수익 (MVP proxy).

---

## 6. Legacy screener 역할

| 기존 | v0.2 shadow 기간 |
|------|------------------|
| 실전 후보 생성 | **Research candidate generator** |
| trade_actions | **영향 금지** |
| QVM 점수 | 참고·비교 |
| 하케다카 | 보조 촉매 (향후) |

**최종 분류:** alpha_v0.2 classifier. legacy는 `alpha_candidates.csv`와 diff.

---

## 7. 산출물

| 파일 | 용도 |
|------|------|
| `outputs/alpha_v0_2_classification.csv` | 종목별 분류표 |
| `outputs/alpha_v0_2_shadow.json` | 전체 스냅샷 |
| `outputs/alpha_v0_2_shadow_log.csv` | 일별 요약 append |
| `outputs/alpha_v0_2_legacy_diff.json` | legacy vs v0.2 diff |
| `daily_report.md` | Alpha v0.2 Shadow 섹션 |

---

## 8. Acceptance (MVP)

| ID | 조건 |
|----|------|
| A-01 | v1.0.2 trade_actions 변경 없음 |
| A-02 | shadow 출력만 |
| A-03 | Core/Candidate/Legacy/Exit/Excluded 중 하나 |
| A-04 | Quality fail → 신규매수 불가 |
| A-05 | Momentum fail → 신규매수 불가 |
| A-06 | alpha overweight → 신규 alpha buy 0 |
| A-07 | 단일종목 hard max 초과 → 증액 불가 |
| A-08 | 섹터 cap pressure 기록 |
| A-09 | benchmark 비교 필드 |
| A-10 | legacy diff 로그 |

---

## 9. 90~120일 후 결정

v0.2가 legacy보다 **보수적·일관적**이고 Core vs Legacy 분류가 사후 수익과 맞으면 → legacy 판단을 v0.2로 **대체 검토**.  
그 전까지 **실거래 연결 금지**.

---

## 한 줄

**집(v1.0.2)은 그대로, 알파 엔진만 별채로 새로 짓고 90~120일 병렬 비교한다.**
