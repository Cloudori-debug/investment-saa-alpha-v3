



# SAA 초과수익 갭 해소 — 설계 및 명세서 (P5)

> **작성 배경:** Claude 리뷰 세션에서 "이 프로그램이 SAA 리밸런싱을 수익률 면에서 이길 수 있게 설계되어 있는가"를 검증한 결과, 스톡피킹(알파) 품질 이전에 **3가지 구조적 갭**이 확인됨. 본 문서는 그 갭을 좁히기 위한 설계·구현 명세.
> **작성일:** 2026-07-08
> **대상 저장소:** `C:\Cursor\multi_asset_trigger_portfolio`
> **전달 대상:** 커서(Cursor) — 구현 담당
> **진행:** 작업 A **완료** · 작업 B **완료** · 작업 C **완료** (2026-07-08) — P5 갭 해소 1차 닫힘

---

## 구현 상태

| 작업 | 상태 | 산출물 |
|------|------|--------|
| **A Core ETF 미집행 진단** | **완료** | `src/validation/core_etf_blocking_duration.py`, `outputs/core_etf_blocking_duration.json` |
| **B 기회비용 추적** | **완료** | `compute_core_saa_gap_opportunity_cost()`, `outputs/core_saa_gap_opportunity_cost.json` |
| **C 백테스트 비용모델** | **완료** | `data/cost_assumptions.yaml`, `src/backtest/cost_model.py`, Gross/Net + quality 라벨 |

### 작업 C 실측 (2026-07-08)

- 사용 일수 **16** · quality=`insufficient` → 상단 **"예측력 판단 불가 — 참고용"** 강제
- Gross Top-5 excess **2.00%** → Net **1.47%** (왕복 53bp = 15+20+18)
- `--lookback-days` CLI 파라미터 추가
- gate/policy 미변경 · Actual Buy Allowed=0 · `legacy_backlog_count=34`
- tests: `test_alpha_backtest_cost_model.py` **4 passed**

## 0. 변경 금지 영역 (절대 준수)

이 스펙의 모든 작업은 **판단·표시·추적 로직**에 한정되며, 아래 영역은 이번 작업 범위에서 **완전히 제외**한다.

| 영역 | 이유 |
|------|------|
| `gate` threshold / `policy_cap` 로직 | `docs/RUN_MODE_POLICY.md`에서 이미 변경 금지로 고정됨 |
| `target_write` / `approval_bridge` | 사람 승인 없는 자동 매수·매도 경로 신설 금지 |
| `Actual Buy Allowed` 계산식 | 안전 불변식 — 이번 작업으로 값이 바뀌면 안 됨 |
| `execution_scope` / `manual_regime` 판정 로직 | 매크로 판단은 원장님의 수동 영역 (시스템이 자동 완화하지 않음) |

이번 스펙의 작업 3가지는 전부 **"기존 게이트가 왜/얼마나 기회비용을 만드는지 드러내고, 그 안에서 합법적으로 열려 있는 실행을 놓치지 않는지 진단하는 것"**이지, 게이트 자체를 느슨하게 만드는 것이 아니다.

---

## 1. 문제 정의 요약

| # | 문제 | 확인된 근거 | 이번 스펙에서의 성격 |
|---|------|-------------|----------------------|
| A | **Core SAA 슬리브 미집행 (캐시 드래그)** | `positions.csv` 현금·단기채 실비중 66.28% vs `target_portfolio.csv` 목표 ~29%. `core_etf_permission_diagnostics.json`: `eligible_etf_underweight_count=11`, `hypothetical_etf_buy_count_if_unrestricted=11` — **집행 가능한 후보가 이미 11건 존재하는데 0건 집행** | 진단 정밀화 + 조건 충족 시 자동 반영 확인 |
| B | **기회비용 미추적 (portfolio-level)** | `missed_upside_from_gate_mtd_proxy`, `avoided_drawdown_from_gate_mtd_proxy`가 kr_alpha 개별 종목 신호 차단분만 집계 (`gate_opportunity_cost_count=0`이라 상시 0) — 포트폴리오 전체의 캐시 드래그는 추적 안 됨 | 신규 지표 추가 |
| C | **알파 백테스트 비용 미반영·표본 부족** | `src/backtest/alpha_backtest.py`에 수수료/슬리피지 코드 0건. 16일 샘플, quintile 비단조 | 백테스트 로직 보강 (신규 코드 추가, 기존 산출물 대체 아님) |

---

## 2. 작업 A — Core ETF 미집행 원인 정밀 진단 + 상태 노출

### 2.1 현재 메커니즘 (확인됨)

`execution_scope=ETF_ONLY`는 **"ETF 매수 허가"가 아니다.** 실제 ETF 신규매수는 별도 게이트 `core_etf_permission`(현재 `RESTRICTED`)이 `ALLOWED`여야 하고, 이는 다음에 의해 막힘:

```
data_gate=YELLOW (portfolio_gate=YELLOW, health_gate=YELLOW, tier2_provenance stale 1건)
  → core_etf_permission=RESTRICTED
  → etf_new_buy_state=REVIEW_ONLY
  → Actual Buy Allowed=0
```

`core_etf_permission_diagnostics.json`은 이미 `eligible_etf_underweight_count=11`을 계산하고 있으나, **"11건이 며칠째 막혀 있는지", "어떤 개별 원인(YELLOW driver)이 가장 오래 지속되고 있는지"는 추적하지 않음.**

### 2.2 설계

신규 파일: `src/validation/core_etf_blocking_duration.py`

```python
def compute_core_etf_blocking_duration(
    decision_log_path: Path,
    as_of: str,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """decision_log.jsonl의 bundle_reconciliation 이벤트를 훑어
    core_etf_permission이 RESTRICTED/BLOCKED로 유지된 연속 일수와
    가장 자주 등장한 restriction_reason을 집계한다.
    """
```

**출력 스키마** — `outputs/core_etf_blocking_duration.json`:

```json
{
  "as_of": "2026-07-08",
  "core_etf_restricted_days_current_streak": 0,
  "core_etf_restricted_days_last_30d": 0,
  "dominant_restriction_reason": "data_gate_yellow",
  "reason_frequency_last_30d": {
    "data_gate_yellow": 0,
    "policy_cap_active": 0,
    "health_gate_yellow": 0,
    "target_guard_conflict": 0
  },
  "eligible_etf_underweight_count_today": 11,
  "note": "진단 전용 — gate/policy_cap 미변경. Actual Buy Allowed에 영향 없음."
}
```

### 2.3 daily_report.md 노출 (표시만 추가, 판단 로직 불변)

`## SAA 재개 조건` 섹션 하단에 한 줄 추가:

```
- **Core ETF 잠김 지속**: {N}일 연속 (주 원인: {dominant_restriction_reason}) · 즉시 집행 가능 후보 {eligible_count}건
```

### 2.4 완료 기준

- [ ] `core_etf_blocking_duration.json` 산출물 생성, `decision_log.jsonl` 파싱 검증
- [ ] `daily_report.md`에 위 한 줄 반영, `report_clarity_validation`에 새 실패 케이스 추가 없음
- [ ] 신규 단위테스트 — 연속 RESTRICTED 3일치 mock decision_log로 streak=3 계산 검증
- [ ] gate/policy_cap 파일 diff 없음 (mtime 확인)

---

## 3. 작업 B — Portfolio-level 기회비용 추적

### 3.1 현재 갭

`_satellite_proxy_returns()` (`src/alpha/performance_dashboard.py:342`)는 **kr_alpha 종목 단위** `gate_rows`만 순회한다. Core SAA 슬리브(글로벌주식·채권·리츠 등)가 목표 대비 얼마나 미집행 상태였고, 그 기간 해당 자산이 실제로 얼마나 움직였는지는 전혀 계산하지 않는다.

### 3.2 설계

신규 함수: `src/alpha/performance_dashboard.py`에 `_core_saa_gap_opportunity_cost()` 추가 (기존 함수 대체 아님, 병렬 추가).

```python
def compute_core_saa_gap_opportunity_cost(
    data_dir: Path,
    output_dir: Path,
    as_of: str,
) -> dict[str, Any]:
    """target_portfolio.csv 대비 실제 positions.csv 비중 갭 × 해당 티커의
    기간 가격수익률(ticker_return_mtd)을 곱해, '목표대로 채워져 있었다면'의
    이론적 수익과 실제 수익의 차이를 계산한다.

    주의: 이것은 사후 진단(shadow)이며 target_write/Actual Buy Allowed에
    어떤 영향도 주지 않는다.
    """
```

**계산 방식 (Modified 방식, capital-agnostic):**

```
for each asset_group / ticker in target_portfolio.csv:
    gap_pct = target_weight - actual_weight   # positions.csv 기준
    if gap_pct > threshold(0.5%p):
        ticker_ret = ticker_return_mtd(prices, ticker, as_of)
        opportunity_cost_contrib = gap_pct * ticker_ret   # 부호 그대로 (놓친 상승은 +, 피한 하락은 -)

core_saa_gap_opportunity_cost_mtd = sum(opportunity_cost_contrib)
```

**출력 스키마** — `alpha_performance_dashboard.json`에 신규 필드 추가:

```json
{
  "core_saa_gap_opportunity_cost": {
    "method": "target_weight_gap_x_ticker_price_return",
    "as_of": "2026-07-08",
    "total_gap_pct": 37.4,
    "opportunity_cost_mtd_pct": null,
    "by_bucket": [
      {"asset_group": "global_beta", "gap_pct": 27.08, "ticker_return_mtd": null, "contrib_pct": null, "reason": "insufficient_price_history_or_missing"},
      {"asset_group": "cash_short_bond", "gap_pct": -41.02, "ticker_return_mtd": null, "contrib_pct": null}
    ],
    "quality": "shadow_diagnostic_only",
    "limitation": "짧은 표본·가격 결측 시 개별 항목 null. 전체 합계도 결측 항목이 있으면 보수적으로 null 처리.",
    "disclaimer": "This does NOT change Actual Buy Allowed, target_write, or any execution gate. Diagnostic only."
  }
}
```

### 3.3 daily_report.md 노출

`## SAA-relative Alpha Dashboard` 섹션에 한 줄 추가:

```
- **Core SAA 갭 기회비용(MTD, shadow)**: {opportunity_cost_mtd_pct}%p (총 갭 {total_gap_pct}%p) — 실행 게이트 미변경, 진단 전용
```

값이 `null`인 케이스(가격 결측 등)는 반드시 `None`/`n/a`로 표시하고 절대 0으로 표시하지 않는다 (이전 kospi 0.0 버그와 동일한 실수 방지 — `_fmt_optional_pct` 재사용).

### 3.4 완료 기준

- [ ] 신규 필드가 `report_clarity_validation.py`의 "None을 숫자처럼 표시 금지" 규칙을 통과
- [ ] 단위테스트: 갭 100%p·가격상승 10% mock → contrib 계산 정확성 검증
- [ ] 단위테스트: 가격 결측 시 해당 항목 `null` (0 아님) 검증
- [ ] `Actual Buy Allowed`, `target_write_count` 등 안전 지표 값 불변 확인 (회귀 테스트)

---

## 4. 작업 C — 알파 백테스트 비용 모델 + 표본 확대 설계

### 4.1 현재 갭

`src/backtest/alpha_backtest.py`: 비용(수수료·슬리피지·세금) 반영 코드 없음. 표본 16일, quintile 비단조.

### 4.2 설계 — 비용 모델 (1차, 표본 확대와 분리 가능)

```python
# src/backtest/cost_model.py (신규)
DEFAULT_COST_ASSUMPTIONS = {
    "commission_bps": 15,       # 매수+매도 왕복 증권사 수수료 가정 (조정 가능 파라미터)
    "slippage_bps": 20,        # 코스피 중소형주 평균 슬리피지 가정
    "securities_tx_tax_bps": 18,  # 국내 매도 시 증권거래세 (2026 기준 확인 필요 — 원장님 재확인 요망)
}

def apply_round_trip_cost(gross_return_pct: float, holding_days: int, assumptions: dict) -> float:
    """총비용(bps)을 편도가 아닌 왕복 기준으로 차감."""
```

**주의:** `securities_tx_tax_bps` 값은 세율 변경 가능성이 있어 **하드코딩 대신 `data/cost_assumptions.yaml`로 분리**하고, 문서 상단에 "가정치이며 실제 세율은 원장님이 확인 후 조정" 문구 필수.

### 4.3 설계 — 표본 확대

`alpha_backtest.py`의 `--lookback-days` 파라미터 추가, 최소 실행 기준을 다음과 같이 조정:

| quality | 표본일수 | 표시 |
|---------|----------|------|
| `insufficient` | < 60일 | "예측력 판단 불가 — 참고용" 강제 라벨 |
| `preliminary` | 60~180일 | "예비 검증 — 확정 아님" |
| `provisional` | 180일+ | "잠정 검증" (그래도 "확정된 알파"라고 표현 금지) |

### 4.4 출력 스키마 확장 — `alpha_backtest_report.md`

```
## Alpha Lite Backtest (cost-adjusted)
- 사용 일수: {N}일 · 품질: {insufficient|preliminary|provisional}
- Gross Top-5 초과수익: X.XX%
- Cost 가정: 수수료 {commission_bps}bp + 슬리피지 {slippage_bps}bp + 거래세 {tax_bps}bp (왕복)
- **Net Top-5 초과수익 (비용 차감 후)**: X.XX%
- Quintile monotonic: Yes/No
```

### 4.5 완료 기준

- [ ] `data/cost_assumptions.yaml` 신설, 기본값 문서화 + "가정치, 확인 필요" 명시
- [ ] `alpha_backtest_report.md`에 Gross/Net 병기, quality 라벨 강제
- [ ] 표본 60일 미만이면 리포트 최상단에 "예측력 판단 불가" 문구 자동 삽입
- [ ] 단위테스트: cost 적용 전/후 수치 차이 검증, quality 라벨 임계값 검증

---

## 5. 우선순위 및 순서

| 순위 | 작업 | 근거 |
|------|------|------|
| **1** | 작업 A (Core ETF 미집행 진단) | 이미 11건 집행 가능 후보가 존재 — 가장 빠르게 "왜 안 사는지"를 드러낼 수 있음. 판단 로직 불변, 진단만 추가라 리스크 최소 |
| **2** | 작업 B (기회비용 추적) | A의 산출물을 입력으로 재사용 가능. "SAA 대비 이기고 있는지"를 정량화하는 핵심 지표 |
| 3 | 작업 C (백테스트 비용모델) | 알파 슬리브 자체의 장기 유효성 검증 — 표본이 쌓여야 의미가 생기므로 가장 급하지 않음 |

세 작업 모두 **서로 독립적**이라 병렬 진행 가능하나, 검토 부담을 줄이려면 A → B → C 순서로 한 건씩 패치·검증 권장 (지난 NAV MTD 패치와 동일한 방식).

---

## 6. 공통 검증 절차 (각 작업 공통)

```powershell
# 1) 단위테스트
python -m pytest tests/test_core_etf_blocking_duration.py -q   # 작업 A
python -m pytest tests/test_core_saa_gap_opportunity_cost.py -q # 작업 B
python -m pytest tests/test_alpha_backtest_cost_model.py -q     # 작업 C

# 2) 안전 불변식 회귀 확인 (필수, 매 작업 후)
python scripts/verify_claude_review.py
# → actual_buy_allowed_zero, target_write_zero, operation_blocking_failures_empty 는 계속 pass여야 함

# 3) gate/policy 파일 미변경 확인
# (mtime 또는 diff로 src/policy_cap.py, src/execution_scope.py, src/execution_guards.py,
#  src/alpha/target_write_audit.py, src/validation/bundle_consistency.py 불변 확인)
```

---

## 7. 커서에게 전달할 요약 프롬프트

```text
SAA_ALPHA_GAP_CLOSURE_SPEC.md (P5) 구현을 요청합니다.

저장소: C:\Cursor\multi_asset_trigger_portfolio
문서: docs/SAA_ALPHA_GAP_CLOSURE_SPEC.md

우선순위 1건씩 진행:
1) 작업 A — core_etf_permission이 며칠째 RESTRICTED인지, 어떤 이유가 지배적인지
   진단 산출물(core_etf_blocking_duration.json) 추가. gate/policy_cap 로직 변경 없음.
2) 작업 B — target_portfolio.csv 대비 실제 비중 갭 × 가격수익률로 포트폴리오 레벨
   기회비용(core_saa_gap_opportunity_cost) 계산 추가. Actual Buy Allowed 등
   실행 지표 불변.
3) 작업 C — alpha_backtest.py에 비용모델(수수료/슬리피지/거래세) 반영 +
   표본 부족 시 "예측력 판단 불가" 라벨 강제.

각 작업 완료 후: verify_claude_review.py 재실행 + gate/policy/approval_bridge
파일 미변경 확인 결과를 함께 보고해주세요.
```

---

## 8. 한계 및 판단 보류 사항 (명시)

- 작업 B의 "기회비용"은 어디까지나 **사후 shadow 계산**이며, 실제로 그 시점에 매수했다면 발생했을 슬리피지·타이밍 차이는 반영하지 못한다. 상한선(upper bound) 추정치로 해석해야 한다.
- 작업 C의 비용 가정치(수수료·거래세 bps)는 **원장님이 실제 증권사 수수료율과 최신 세율로 확인 후 조정 필요** — 이 문서의 숫자는 자리표시자(placeholder)다.
- 세 작업 모두 구현 후에도 "SAA를 이기고 있다"는 결론은 **최소 수개월의 비용 차감 후 실측 데이터**가 쌓여야 내릴 수 있다. 이 스펙은 그 판단에 필요한 계측 인프라를 만드는 것이지, 즉시 초과수익을 만들어내는 것이 아니다.
