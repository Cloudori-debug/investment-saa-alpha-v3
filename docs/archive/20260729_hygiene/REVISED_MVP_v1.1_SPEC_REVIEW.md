# Revised MVP v1.1 스펙 검토

> **검토 대상:** `revised_mvp_v1_1_spec.md` (Downloads)  
> **대조 기준:** v1.0.2 코드베이스 · `docs/OPS_POLICY_v1.0.2.md`  
> **검토일:** 2026-06-19

---

## 총평

**방향은 맞다.** “전체 재작성”보다 **결정 레이어(decision layer) 재설계** + strangler pattern은 현재 코드(`compass`, `policy_cap`, `execution_scope`, `trigger_reviews`, `mismatch_check`)와 잘 맞는다.

다만 문서 이름은 MVP v1.1이지만 실질 내용은 **E급 구조 확장**(8칸 SAA + TAA 재정의 + drawdown ladder + 실행 5게이트)에 가깝다. `OPS_POLICY_v1.0.2.md`의 **“90일 내 E 보류”** 와 직접 충돌하므로, **지금 착수 스펙**이 아니라 **D+90 이후 후보 설계안**으로 두는 것이 맞다.

**권장:** v1.1a **shadow mode**(진단·로그만) → 90일 후 필요 시 v1.1a 실행 / v1.1b(8칸 SAA).  
**문서:** `docs/MVP_v1.1a_SHADOW_MODE.md` · `docs/MVP_v1.1a_SPEC.md`

---

## 문제 진단 — 현재 시스템과의 정합

| 스펙 지적 | 판정 | 근거 |
|-----------|------|------|
| `cash_short_bond`에 현금·단기채·(개념상) duration 혼재 | **맞음** | `data/asset_group_labels.yaml` — “미국 듀레이션 채권 아님”이지만 구조상 한 칸(SAA **40%**) |
| `kr_alpha`가 SAA/TAA와 충돌 | **맞음 (핵심)** | `data/saa_profiles.yaml` — `kr_alpha: 31%`, TAA에서 ±5~15p 직접 조작 |
| TAA가 참여보다 차단 게이트처럼 작동 | **부분 맞음** | TAA tilt는 있으나 실행은 `policy_cap`·`data_gate`·`dry_run`·`execution_scope`가 더 강함 |
| Data / Policy / Opportunity / Execution 혼재 | **맞음** | v1.0.1 technical/operational 분리했으나 **“얼마까지 살 수 있는가”** 금액 산출 없음 |
| 급락 분할매수 모듈 부재 | **부분 맞음** | `trigger_reviews.py` + `trigger_rules.yaml` — -5/-10/-15 **검토 알림**만, buy reserve % 없음 |
| target vs ticker 합 불일치 | **맞음** | `src/compass/mismatch_check.py`(0.5%p) + kr_alpha 예산 스케일 경고 반복 |

**결론:** 6개 중 4개 정확. TAA·drawdown은 “없다”보다 **“미완성 / 실행 분리 안 됨”** 이 정확한 표현.

---

## 설계 원칙 — 타당성

| 원칙 | 평가 |
|------|------|
| SAA = 기준 포트, 자주 변경 금지 | 타당 |
| TAA = 제한적 overlay | 타당 — 현재 `taa_tilts`와 방향 일치, 실행과 분리 필요 |
| 급락 매집 = drawdown ladder (TAA 아님) | 타당 — CRISIS `kr_alpha: -15`와 분리 |
| Alpha = 위성 슬리브 | 타당 — 현재 SAA 31%와 모순 해소 |
| 실행 = 금지 + 허용 범위 산출 | 타당 — v1.0.1 위에 자연스럽게 확장 |

---

## 약점·누락

### 1. SAA 예시 vs 현재 운용

| | 스펙 v1.1 예시 | 현재 `defensive_balanced` |
|--|----------------|---------------------------|
| cash 계열 | 35% (3분할) | `cash_short_bond` **40%** |
| alpha | **10%** (max 20) | `kr_alpha` **31%** (min 20) |
| global equity | **30%** | `global_beta` **10%** |

8칸 분리는 개념적으로 맞지만, **비중 예시 적용 = 포트 전략 변경**. AC에서 “스키마 분리”와 “SAA 숫자 변경”을 분리해야 함.

### 2. v1.0.2 look-through 충돌

v1.0.2는 **7칸 target 수학 유지 + look-through 진단만** 추가. 8칸 전환 시 `look_through_tags.yaml`, `VALID_ASSET_GROUPS`, gap/trade_actions 전면 마이그레이션. **7→8 alias 기간**이 구현 순서에 없음.

### 3. TAA “월 1회” vs 일별 레짐

`regime_auto.py`가 compass 레짐을 일별 반영 가능. “월 1회 TAA” 도입 시 **일별 policy_cap/compass와 충돌 규칙** 필요.

### 4. drawdown ladder — buy reserve 미정

- buy reserve = `cash_short`인지 별도 슬롯인지 미정
- `trigger_reviews`는 **KOSPI만** (글로벌 -10% 조건 미구현)
- `systemic stress` 정의 없음

### 5. AC #7 “YELLOW 최소 시장참여” — 수치 미정

현재 YELLOW_STABLE → ETF_ONLY + kr_alpha 신규 차단. **최소 %p·대상 자산군** 없으면 테스트 불가.

### 6. 구현 순서 — 난이도 과소평가

strangler pattern이면 **parallel decision engine + diff 리포트**가 0번 단계.

### 7. 90일 운용 방침 미기재

20~30영업일 dry-run, RED 5분류, B/C/D 우선순위가 스펙에 없음.

---

## Acceptance Criteria (AC 1~10)

| AC | 평가 | 비고 |
|----|------|------|
| 1 cash/duration 분리 | 필수 | v1.1b |
| 2~3 SAA/TAA 합 100% | 필수 | `saa_engine.py` 패턴 |
| 4 TAA min/max band | 필수 | `group_bounds` |
| 5 alpha TAA 비조작 | 핵심 | **현재 위반** (`taa_tilts.kr_alpha`) |
| 6 ladder 없으면 급락 신호 금지 | guardrail | v1.1a |
| 7 YELLOW 최소 참여 | 수치 정의 필요 | v1.1a |
| 8 alpha 상한 초과 → 신규 0 | 부분 구현 | `execution_scope` |
| 9 ticker/allocation 0.5%p | **이미 구현** | `mismatch_check.py` |
| 10 리포트 4줄 분리 | UX | v1.1a |

---

## 버전 분리 권장

```
지금 ~ D+90     v1.0.2 동결 · B/C만 조건부
D+90 + dry-run  v1.1a — 5게이트 · ladder · 리포트 (7칸 유지)
반복 mismatch   v1.1b — 8칸 SAA · alpha_satellite · TAA 월간
```

| 버전 | 범위 | 90일 방침 |
|------|------|-----------|
| **v1.1a** | Execution 5게이트 + drawdown ladder + 리포트 4줄 | E 아님 |
| **v1.1b** | 8칸 SAA + alpha 10~20% + TAA overlay | E급 — 기록 근거 후 |

---

## 스펙 보완 5항 (원문에 추가 권장)

1. **전제:** v1.0.2 90일 + `data/ops_weekly_log.md` 12주 + dry-run 20영업일+
2. **7→8 매핑:** `cash_short_bond` → `{cash_short, kr_duration_bond}` alias 1버전
3. **buy_reserve:** 예) `cash_short` 중 ladder 투입 상한 25%
4. **YELLOW 최소 참여:** 예) beta 계열 합 ≥ 해당 SAA 합의 70%
5. **TAA 주기:** 월 1회 산출 / 일별은 gate만 — 충돌 시 `policy_cap` 우선

---

## 최종 판정

| 항목 | 판정 |
|------|------|
| 문제 진단 | 타당 |
| 설계 원칙 | 채택 가치 있음 |
| strangler 전략 | 맞음 |
| 지금 즉시 전체 구현 | **비추천** |
| D+90 방향 문서 | **채택 가능** (v1.1a → v1.1b) |
| 먼저 손댈 부분 | Execution Permission + drawdown ladder (7칸 유지) |
| 가장 위험한 부분 | 8칸 SAA + kr_alpha 31%→10% 동시 변경 |

**한 줄:** 틀린 설계가 아니라 **시기·범위가 큰 설계**. v1.0.2 90일 감사관 모드 후 v1.1a → v1.1b 순이 운영 방침·리스크 모두에 맞다.
