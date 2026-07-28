# Multi-Asset Portfolio System — MVP v1.1a (축약)

> **⚠️ D+90 전 실행 로직 구현 금지.** 지금 착수 범위는 **shadow mode 진단만** — `docs/MVP_v1.1a_SHADOW_MODE.md`  
> **범위 (shadow):** blocked_reason · reviewable_amount · drawdown ladder 진단 · daily 4줄 · ops_shadow_log  
> **유지:** 7자산군 · v1.0.2 execution_scope · SAA 비중 · 실거래 판단  
> **보류 (v1.1b):** 8칸 SAA · kr_alpha 축소 · execution 재정의 · dip-buy 실권한

---

## 목표

v1.0.2 파이프라인은 그대로 두고, **실행 판단만** 다음처럼 분리·출력한다.

1. **무엇이 막혔는가** (게이트별 실패)
2. **무엇이 허용되는가** (범위·금액)
3. **급락 시 얼마까지 검토 가능한가** (ladder, 자동매수 아님)
4. **Alpha는 리서치 vs 실행 권한** (분리 표시)

---

## 설계 원칙 (v1.1a)

- **7자산군 ID 변경 없음** — `cash_short_bond`, `kr_alpha` 등 유지
- SAA/TAA **숫자·프로필 변경 없음** — `defensive_balanced` 그대로
- TAA는 기존 레짐 tilt 유지; v1.1a는 **TAA 로직 재작성 안 함**
- 급락 매집은 **TAA tilt와 출력 분리** — ladder 모듈만 추가
- Alpha screener = 후보 생성; 실행 = **별도 permission 블록**
- 모든 신규매수는 **사람 승인 전 REVIEW_ONLY** (자동매매 없음)

---

## Execution Permission (5게이트)

기존 `technical_status` / `policy_cap` / `operational_status` 위에 **명시적 5블록** JSON·리포트 출력.

| 게이트 | 입력 | pass | fail 시 |
|--------|------|------|---------|
| **Data Gate** | `core_price_gate`, alpha price, fundamentals freshness | GREEN/YELLOW | RED → 신규매수 금지 |
| **Policy Gate** | FSR, 수동 레짐, `policy_cap`, expiry | cap 내 scope | scope 하향 |
| **Risk Gate** | `risk_limits`, kr_alpha/종목/섹터 상한 | band 내 | 초과분 Trim만 |
| **Opportunity Gate** | drawdown ladder 단계, (선택) trigger active | 단계별 **허용 금액** 산출 | 0원 |
| **Execution Gate** | dry-run, acceptance, human approval | REVIEW 또는 EXECUTABLE | WAIT |

**산출물:** `outputs/final_execution_decision.json`에 `gates: { data, policy, risk, opportunity, execution }` 각각 `status`, `reasons[]`, `permissions{}`.

### YELLOW 최소 시장참여 (AC-7, v1.1a 고정값)

`operational_status == YELLOW` 이고 `execution_scope >= ETF_ONLY` 일 때:

- `domestic_beta` + `global_beta` **목표 합계가 0%가 되면 fail**
- **최소 floor:** 두 그룹 합 ≥ max(5%p, SAA baseline 합 × **0.70**)
- RED / NO_TRADE는 예외 (floor 미적용)

---

## Drawdown Ladder MVP

TAA·`taa_tilts`와 **독립 모듈**. `trigger_reviews` 확장.

### buy_reserve 정의

- **소스:** `cash_short_bond` 그룹 목표 비중 중 **ladder 전용 상한 = min(25%p, cash_short_bond final_target × 0.625)**
- **잔여:** ladder 미사용분은 현금성 유지 (별도 슬롯 없음)
- **투입 대상:** Tier A ETF만 (`domestic_beta`, `global_beta`, `hedge_alt`, `income_alt`) — **kr_alpha 제외**

### 단계 (KOSPI drawdown 기준, `market_indicators` recent high)

| KOSPI DD | ladder 단계 | 허용 (buy_reserve 대비) | 조건 |
|----------|-------------|-------------------------|------|
| ≤ -5% | WATCH | 0% | 관찰만 |
| ≤ -10% | L1 | 20% | Data Gate ≠ RED |
| ≤ -15% | L2 | +30% (누적 50%) | + Policy Gate ≠ NO_TRADE |
| ≤ -20% | L3 | +30% (누적 80%) | + VIX 전일 대비 하락 또는 200일선 회복 시도 |
| 추세 회복 신호 | L4 | 잔여 20% | 수동 확인 플래그 |

- **systemic stress:** `manual_regime ∈ {CRISIS, RED}` 또는 `data_gate == RED` → ladder **INACTIVE** (금액 0)
- **글로벌 DD:** v1.1a에서는 **로그만** (S&P drawdown 필드 추가, ladder 계산은 v1.1b)

### AC-6

`drawdown_ladder` 모듈이 `outputs/drawdown_ladder.json`을 쓰지 않으면, 급락 관련 **매수 가능 금액 필드를 출력하지 않음** (WATCH 텍스트만 허용).

---

## Alpha (7칸 유지)

- `kr_alpha` SAA 비중·TAA tilt **변경 없음**
- 리포트에 **Research** vs **Execution permission** 분리:
  - Research: screener 상위 N, Q/V/M, 유동성, 탈락 사유
  - Execution: `alpha_new_buy_allowed: bool`, `alpha_trim_only: bool`, 상한 초과 종목 목록
- **AC-8:** kr_alpha 그룹 current > max band → `alpha_new_buy_allowed = false`

---

## 리포트 상단 4줄 (AC-10)

`daily_report.md` 및 UI 요약:

```
SAA baseline:   {profile} · cash 40% · kr_alpha 31% · … (7그룹 요약)
TAA delta:      {applied_regime} · {group: ±Δp} …
Dip-buy budget: {ladder_stage} · {allowed_krw or %} · {gated_reasons}
Alpha permission: {BLOCK_NEW | ALLOW_REVIEW | TRIM_ONLY} · top5 watchlist 링크
```

---

## v1.1a Acceptance Criteria

| ID | 기준 |
|----|------|
| AC-a1 | `final_execution_decision.json`에 5게이트 블록 존재, 각각 status+reasons |
| AC-a2 | Data RED → opportunity·execution 신규매수 금액 = 0 |
| AC-a3 | `drawdown_ladder.json` 없으면 dip-buy 금액 필드 미출력 (AC-6) |
| AC-a4 | ladder INACTIVE 시 allowed_amount = 0, gated_reasons 비어 있지 않음 |
| AC-a5 | YELLOW + ETF_ONLY 시 beta floor ≥ max(5%p, baseline×0.70) 검증 |
| AC-a6 | kr_alpha 상한 초과 → alpha_new_buy_allowed = false (AC-8) |
| AC-a7 | ticker vs allocation mismatch > 0.5%p → 경고 유지 (기존 `mismatch_check`) |
| AC-a8 | daily_report 상단 4줄 고정 포맷 |
| AC-a9 | v1.0.2 look-through·policy_cap·operating_state **회귀 없음** (기존 테스트 pass) |
| AC-a10 | strangler: `outputs/v1_1a_decision/` 병렬 생성 10영업일 후 기본 출력으로 전환 가능 |

---

## 구현 순서

0. **Parallel engine** — `src/decision/v1_1a/` 신규; 기존 `full_pipeline` 산출 유지, diff 리포트 `outputs/decision_diff.md`
1. **Gate serializer** — `technical_status` + `policy_cap` + `risk_limits` → 5게이트 dict
2. **drawdown_ladder.py** — buy_reserve · 단계 · `drawdown_ladder.json`
3. **Opportunity Gate** — ladder allowed_amount → `final_execution_decision`
4. **Alpha permission block** — execution_scope 기존 로직 → 명시 필드
5. **daily_report 4줄** + acceptance AC-a1~a10
6. **10영업일 parallel dry-run** — v1.0.2 출력과 decision diff 비교
7. **전환** — default 출력을 v1_1a로; CHANGELOG v1.1a

**v1.1b로 미룸:** 8칸 스키마, SAA 숫자 변경, TAA 월간 overlay, 글로벌 ladder, cash/duration 3분할.

---

## v1.1b 트리거 (별도 스펙)

`ops_weekly_log` 12주 후 **아래가 3주 이상 반복**될 때만 v1.1b 착수 검토:

- `cash_short_bond` 내 duration/현금 구분 필요가 **운용상** 반복 언급
- kr_alpha SAA 31% vs 실행 상한 모순으로 mismatch 경고 **주 2회+**
- TAA tilt가 “참여”가 아닌 “전면 차단”으로 **일관 기록**

---

## 재작성 여부

**v1.1a:** allocation/decision **출력 레이어만** 추가. strangler pattern.  
**v1.1b:** allocation 스키마 **부분 재작성** — v1.1a 안정 후.

---

## 한 줄

**v1.1a = 7칸 그대로, “왜 막혔고 얼마까지 검토 가능한지”를 게이트·금액·4줄 리포트로 고정한다.**
