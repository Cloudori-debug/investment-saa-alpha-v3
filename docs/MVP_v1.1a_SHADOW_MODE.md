# MVP v1.1a — Shadow Mode (진단·관측 전용)

> **역할:** v1.0.2 실행 판단은 **변경하지 않음**. 신호 vs 실행, 차단 사유, 검토 가능 금액을 **분리 출력**해 90일 로그를 쌓는다.  
> **참조:** `OPS_POLICY_v1.0.2.md` · `REVISED_MVP_v1.1_SPEC_REVIEW.md` · `MVP_v1.1a_SPEC.md`(실행 로직 버전 — **D+90 전 착수 금지**)

---

## 왜 shadow mode인가

| 선택지 | 판단 |
|--------|------|
| 문서만 + 90일 운용 | 관측 품질 부족 |
| v1.1a 실행 로직 즉시 구현 | v1.0.2 검증 기간 오염 |
| **shadow 진단 레이어만 추가** | **채택** |

---

## 금지 (v1.0.2 동결 유지)

- 8칸 자산군 전환
- SAA 기준 비중 변경
- `kr_alpha` target 축소
- `execution_scope` 재정의
- ETF/alpha 신규매수 **허용 규칙** 변경
- dip-buy **실제 매수 권한** 부여

---

## 허용 (지금 구현)

| 출력 | 설명 |
|------|------|
| `blocked_by[]` | data / health / policy / alpha / dry-run 등 병목 |
| `duration_bond_status` | cash_short vs kr/global duration **개념 분해** (v1.0.2 target 변경 없음) |
| `reviewable_amount_krw` | 조건 충족 시 **이론상** 검토 가능 금액 (실행 아님) |
| `theoretical_gap_krw` | theoretical actions 기준 underweight 갭 |
| `actual_allowed_krw` | v1.0.2 executable actions 기준 (실제 허용) |
| `drawdown_ladder` | KOSPI DD 단계·buy reserve 진단 |
| `daily_report` shadow 4줄 | SAA / TAA / dip / alpha permission 요약 |
| `ops_shadow_log.csv` | 90일 패턴 분석용 일별 1행 |
| `primary_blocker` | blocked_by 중 대표 병목 1개 (우선순위 고정) |
| `benchmark_saa_return_1d/mtd` | 정적 SAA proxy vs 지수 |
| `portfolio_return_mtd` · `vs_saa_mtd` | 포트 MTD (positions 갱신 시) |
| `missed_buy_return_after_5d/20d` | mismatch 후 **사후** 보강 (069500 proxy) |
| `blocked_decision_outcome` | `GOOD_BLOCK` / `BAD_BLOCK` / `NEUTRAL` (20d 후) |

---

## 산출물

| 파일 | 용도 |
|------|------|
| `outputs/shadow_diagnostic.json` | 당일 전체 진단 스냅샷 |
| `outputs/ops_shadow_log.csv` | 누적 관측 (append) |
| `daily_report.md` | 상단 shadow 4줄 + 기존 v1.0.2 요약 |

JSON 상단 `"mode": "shadow"` · `"execution_authority": "v1.0.2"` 고정.

---

## 90일 관측 지표 (핵심 7개)

| 지표 | CSV 필드 |
|------|----------|
| signal vs execution 불일치 | `signal_execution_mismatch` |
| 병목 1순위 | `primary_blocker` |
| ETF 전면 차단 | `etf_fully_blocked` |
| Alpha만 차단 | `alpha_only_blocked` |
| dip ladder | `dip_stage` |
| SAA 대비 MTD | `vs_saa_mtd` |
| 차단 품질 (사후) | `blocked_decision_outcome` |

주간 집계 템플릿 → `data/ops_weekly_log.md` (Shadow 블록)

---

## D+90 → v1.1b 착수 (2~3개 반복)

| 조건 | 근거 |
|------|------|
| ETF trigger 3회+ · 전부 actual=0 | 과보수 |
| mismatch 10회+ | 구조 재검토 |
| `cash_short_bond` 과다 3주+ | 8칸 분리 |
| kr_alpha cap 초과 3주+ | 슬리브 축소 |
| vs SAA -3%p+ | 구조 문제 |
| `BAD_BLOCK` 반복 | 기회비용 |
| dip stage · actual=0 반복 | ladder 필요 |

**v1.1b 후보:** `duration_gap=absent/underweight` + `cash_short` 과다가 **3주+** 반복 → 8~9칸 SAA (`cash_short` / `kr_duration_bond` 분리)

---

## 한 줄

**v1.1a shadow = 설명력 MVP. 돈은 v1.0.2가 결정하고, shadow는 90일 동안 v1.1b가 정말 필요한지 증거를 모은다.**
