



# P5-D — 과거 시세 백필 + Since-Inception 기회비용 — 설계 및 명세서

> **선행 문서:** `docs/SAA_ALPHA_GAP_CLOSURE_SPEC.md` (P5 A/B/C, 완료)
> **작성 배경:** "과거 몇 개월치 데이터를 가져올 수 없나 / 그 기간 투자 못해서 손해가 났는데" 질문에 대한 후속 조치.
> **핵심 전제 (이미 확인됨):** `src/data_refresh/pykrx_bulk.py:438`에 `lookback_start(as_of, 400)` — pykrx로 종목당 최대 400일 일별 시세를 실제로 끌어올 수 있는 기능이 **이미 코드에 존재**함. 이번 스펙은 이 기존 기능을 좁은 범위로 실행하고, 그 결과를 Task B에 연결하는 작업.
> **작성일:** 2026-07-08
> **대상 저장소:** `C:\Cursor\multi_asset_trigger_portfolio`
> **전달 대상:** 커서(Cursor) — 구현 담당, 원칙적으로 이 문서 하나로 끝까지 진행 (예외는 8절 참조)

---

## 0. 변경 금지 영역 (P5와 동일, 절대 준수)

| 영역 | 이유 |
|------|------|
| `gate` threshold / `policy_cap` 로직 | `docs/RUN_MODE_POLICY.md` 고정 |
| `target_write` / `approval_bridge` | 사람 승인 없는 자동 매수·매도 경로 신설 금지 |
| `Actual Buy Allowed` 계산식 | 안전 불변식 |
| `execution_scope` / `manual_regime` 판정 로직 | 원장님의 수동 영역 |

이번 작업 2개(D1 시세 백필, D2 since-inception 기회비용)는 **데이터 수집 + 진단 계산**이며, 실행 게이트·매수 허가와 무관하다.

---

## 1. 문제 정의 및 결론 (재확인)

| 구분 | 결론 |
|------|------|
| 백테스트 표본 부족 (Task C `quality=insufficient`) | **과거 시세 백필로 지금 바로 해결 가능** (D1) |
| "그 기간 투자 못해서 난 손해" | **데이터 백필로 되돌릴 수 없음(sunk)**. 대신 실제로 얼마나 놓쳤는지 정확한 숫자로 확정 가능 (D2) |

D2는 D1이 채운 과거 시세(특히 069500·core SAA ETF들의 6/17 이후 가격)에 의존하므로 **D1 → D2 순서 고정**.

---

## 2. 현재 데이터 상태 (확인됨)

`data/prices_history.csv`:
- 4/17, 5/17, 6/17 — 월 1회 스냅샷만 존재 (희소)
- 6/22 이후 — 일별 (시스템 가동 시점부터)
- **069500(KOSPI200 proxy)은 6/26 단 1건뿐** — `stale_price`로 계속 결측 처리되는 원인

`decision_log.jsonl` 최초 기록: **2026-06-17T02:52:59** → 이번 스펙의 **inception_date 기본값 = `2026-06-17`**로 고정 (원장님이 실제 계좌 개시일과 다르다고 하시면 그때만 조정).

---

## 3. 작업 D1 — 과거 시세 백필 (좁은 범위, 안전 우선)

### 3.1 스코프 고정 (임의 확장 금지)

전체 유니버스(2,729종목) 백필은 **이번 스펙 범위 아님** — pykrx 비공식 API rate limit 리스크가 크고, D2에 당장 필요하지도 않음. 이번엔 다음 **13종목만** 대상으로 한다.

| 그룹 | 티커 |
|------|------|
| 벤치마크 proxy | `069500` (KOSPI200) |
| Core SAA (kr_alpha 제외) | `data/target_portfolio.csv`에서 `asset_group != "kr_alpha"`인 전 종목 (360750, 195930, 238720, 195980, 458730, 161510, 411060, 148070, 308620, 157450, 357870, 352560) + `CASH`는 가격 대상 아니므로 제외 → **실질 12종목** |

`CASH`는 시세가 없으므로 D1 대상에서 제외(계산 시 return=0 고정 처리는 D2에서 별도 처리).

### 3.2 신규 스크립트: `scripts/backfill_price_history.py`

```python
"""P5-D1 — 좁은 범위 과거 시세 백필 (KOSPI200 proxy + Core SAA 티커).

Does NOT touch gate/policy_cap/target_write. Read-only price collection.
Idempotent: 기존 (ticker, date) 행은 덮어쓰지 않고 skip.
"""
import argparse

def resolve_backfill_tickers(data_dir: Path) -> list[str]:
    """069500 + target_portfolio.csv의 kr_alpha 제외 티커. CASH 제외."""

def backfill_price_history(
    data_dir: Path,
    tickers: list[str],
    as_of: str,
    lookback_days: int = 400,
    *,
    krx_login: Any | None = None,   # 기존 pykrx_collect_main의 로그인 객체 재사용
    dry_run: bool = False,
) -> dict[str, Any]:
    """기존 src.data_refresh.pykrx_bulk의 OHLCV 호출부를 재사용.
    prices_history.csv에 (ticker, date) 기준 append-only merge.
    """
```

**동작 규칙:**
- `stock.get_market_ohlcv(compact_start, compact_end, ticker)` — 기존 `pykrx_bulk.py`의 호출 방식 그대로 재사용 (신규 API 로직 만들지 말 것)
- 기존 `prices_history.csv`에 이미 있는 `(ticker, date)` 조합은 **절대 덮어쓰지 않음** — 순수 추가만
- 병합 후 `ticker, date` 기준 정렬 유지
- KRX 로그인이 설정 안 돼 있으면 **예외로 죽지 말고** `{"success": False, "reason": "krx_credentials_missing"}` 반환 — 이 경우 아래 8절 참조(원장님 확인 필요 지점)
- `sleep_sec` 등 기존 rate-limit 완충 로직 그대로 사용 (13종목이라 실행 시간은 짧을 것으로 추정)

### 3.3 CLI

```powershell
python -m scripts.backfill_price_history --lookback-days 400
# 또는 dry-run으로 대상 티커/기간만 확인
python -m scripts.backfill_price_history --lookback-days 400 --dry-run
```

### 3.4 산출물

`outputs/price_backfill_report.json`:
```json
{
  "schema_version": "1.0",
  "as_of": "2026-07-08",
  "requested_tickers": ["069500", "360750", "..."],
  "lookback_days": 400,
  "rows_added": 0,
  "rows_skipped_existing": 0,
  "tickers_failed": [],
  "krx_login_status": "ok",
  "note": "read-only price backfill — gate/policy/target_write 미변경"
}
```

### 3.5 완료 기준

- [ ] 13종목 × 최대 400일 범위로 실행, `prices_history.csv`에 기존 행 훼손 없이 추가됐는지 확인 (행 수 증가, 기존 값 불변)
- [ ] 재실행해도 `rows_added=0`(멱등성) — 중복 삽입 없음
- [ ] `069500`이 6/17 전후로 데이터가 채워졌는지 확인 (`ticker_return_mtd(prices, "069500", as_of)`가 더 이상 `stale_price` 아님)
- [ ] 단위테스트는 **실제 pykrx 네트워크 호출 없이 mock으로만** 작성 (`stock.get_market_ohlcv`를 stub) — CI에서 네트워크 의존 금지
- [ ] gate/policy_cap 파일 diff 없음

---

## 4. 작업 D2 — Since-Inception 포트폴리오 레벨 기회비용

### 4.1 설계

신규 함수 (기존 MTD 버전과 병렬, 대체 아님): `src/alpha/performance_dashboard.py`

```python
INCEPTION_DATE_DEFAULT = "2026-06-17"  # decision_log.jsonl 최초 기록일

def compute_core_saa_gap_opportunity_cost_since_inception(
    data_dir: Path,
    output_dir: Path,
    as_of: str,
    *,
    inception_date: str = INCEPTION_DATE_DEFAULT,
    gap_threshold_pct: float = _GAP_THRESHOLD_PCT,
) -> dict[str, Any]:
    """오늘자 target vs 실제 비중 갭(gap_pct)이 inception_date부터 오늘까지
    '대체로 유지됐다'고 가정하고, 그 갭에 inception_date→as_of 누적
    가격수익률을 곱해 since-inception 기회비용을 근사(approximation)한다.

    한계(반드시 결과에 포함):
    - 실제 과거 매일의 갭은 변동했을 수 있음 — 오늘 스냅샷 갭으로 근사.
    - 상한선(upper bound) 성격의 shadow 추정치, 운용 판단 근거 아님.

    Does NOT change Actual Buy Allowed / target_write / any execution gate.
    """
```

**계산 방식:**
```
gap_pct = 기존 compute_core_saa_gap_opportunity_cost()와 동일 로직 재사용 (오늘 스냅샷)
for each ticker:
    ret_since_inception = ticker_cum_return(prices, ticker, inception_date, as_of)  # 신규 헬퍼
    contrib = (gap_pct / 100) * ret_since_inception
since_inception_opportunity_cost_pct = sum(contrib), 단 결측 있으면 총합 null (D1과 동일 원칙)
```

`ticker_cum_return(prices, ticker, start, end)` 신규 헬퍼는 `src/alpha/benchmark_data.py`에 `ticker_return_mtd`와 동일한 stale/결측 규칙(절대 가짜 0 반환 금지)을 적용해 추가.

### 4.2 출력 스키마 — `outputs/core_saa_gap_opportunity_cost_since_inception.json`

```json
{
  "method": "target_weight_gap_x_ticker_cumulative_return_since_inception",
  "inception_date": "2026-06-17",
  "as_of": "2026-07-08",
  "total_gap_pct": 104.19,
  "opportunity_cost_since_inception_pct": null,
  "by_bucket": [
    {"asset_group": "global_beta", "gap_pct": 25.85, "ticker_cum_return_since_inception": null, "contrib_pct": null}
  ],
  "quality": "shadow_diagnostic_only | partial_price_coverage | missing_inception_price",
  "limitation": "오늘 스냅샷 갭이 inception 이후 계속 유지됐다고 가정한 근사치(상한선 성격). 실제 일별 갭 변화·슬리피지·매매 타이밍 미반영.",
  "disclaimer": "This does NOT change Actual Buy Allowed, target_write, or any execution gate. Diagnostic only — approximation."
}
```

### 4.3 daily_report.md 노출

기존 `## SAA-relative Alpha Dashboard` 섹션, D1(기존 MTD 기회비용) 줄 바로 아래 추가:

```
- **Core SAA 갭 기회비용 (since 2026-06-17, shadow, 근사)**: {opportunity_cost_since_inception_pct}%p — 오늘 갭이 가동 이후 유지됐다는 가정, 상한선 추정치
```

`null`은 항상 `n/a`로 표시 (0 금지 — 기존 P4e/P5-B 규칙과 동일).

### 4.4 완료 기준

- [ ] `ticker_cum_return()` 단위테스트: 정상 구간, inception일 가격 결측 시 `null`, `days_stale` 과다 시 `null`
- [ ] `compute_core_saa_gap_opportunity_cost_since_inception()` 단위테스트: mock으로 gap×누적수익 계산 정확성, 결측 시 총합 `null`
- [ ] `report_clarity_validation`에 이 신규 필드로 인한 새 실패 없음
- [ ] `Actual Buy Allowed`, `target_write_count` 등 안전 지표 불변 (회귀 테스트)
- [ ] D1 백필 실행 후에 D2를 돌려 `069500` 등 핵심 티커의 `quality`가 `missing_inception_price`에서 벗어나는지 확인

---

## 5. 실행 순서 (고정)

1. D1 스크립트 실행 (`--dry-run`으로 먼저 대상 확인 → 정식 실행)
2. `outputs/price_backfill_report.json` 확인 — `krx_login_status: ok`, `tickers_failed: []`
3. D2 함수 구현 및 `outputs/core_saa_gap_opportunity_cost_since_inception.json` 생성
4. `daily_report.md`에 since-inception 줄 반영
5. 공통 검증 (6절)

---

## 6. 공통 검증 절차

```powershell
# 단위테스트 (네트워크 mock, 실제 pykrx 호출 없음)
python -m pytest tests/test_backfill_price_history.py -q
python -m pytest tests/test_core_saa_gap_opportunity_cost_since_inception.py -q

# 안전 불변식 회귀
python scripts/verify_claude_review.py
# → actual_buy_allowed_zero, target_write_zero, operation_blocking_failures_empty 계속 pass

# gate/policy 파일 미변경 확인 (mtime)
# src/policy_cap.py, src/execution_scope.py, src/execution_guards.py,
# src/alpha/target_write_audit.py, src/validation/bundle_consistency.py
```

---

## 7. 커서에게 전달할 요약 프롬프트

```text
P5D_HISTORY_BACKFILL_SINCE_INCEPTION_SPEC.md 구현을 요청합니다.

저장소: C:\Cursor\multi_asset_trigger_portfolio
문서: docs/P5D_HISTORY_BACKFILL_SINCE_INCEPTION_SPEC.md

순서 고정 (D1 → D2):
1) D1 — scripts/backfill_price_history.py 신규 작성.
   대상은 069500 + target_portfolio.csv의 kr_alpha 제외 티커(12종목)만.
   전체 유니버스 백필은 이번 범위 아님. 기존 pykrx_bulk.py의 OHLCV 호출 재사용,
   기존 prices_history.csv 행은 절대 덮어쓰지 않고 append-only.
   KRX 로그인 미설정 시 예외 없이 실패 사유만 리포트.
2) D2 — compute_core_saa_gap_opportunity_cost_since_inception() 추가.
   inception_date 기본값 2026-06-17. 오늘 갭 스냅샷 × since-inception
   누적수익률로 근사 계산, 결측 시 총합 null(가짜 0 금지).
   daily_report.md에 기존 MTD 기회비용 줄 아래 한 줄 추가.

gate/policy_cap/target_write/approval_bridge/Actual Buy Allowed 전부 미변경.
단위테스트는 pykrx 네트워크 호출을 mock 처리(CI에서 실제 API 호출 금지).

완료 후: verify_claude_review.py 재실행 결과 + gate/policy 파일 mtime 불변
확인 결과를 함께 보고해주세요.
```

---

## 8. 원장님 확인이 실제로 필요한 유일한 지점

이 문서는 원칙적으로 커서가 끝까지 진행할 수 있도록 작성했다. **단 하나, D1 실행 전에 확인이 필요하다:**

- **KRX ID/PW가 UI 설정 탭에 등록돼 있는지** — 안 돼 있으면 D1은 실행되지 않고 `krx_credentials_missing`으로 실패 보고만 하게 설계했다. 이 경우 원장님이 자격증명을 등록하신 후 재실행하면 된다.

그 외 스코프(13종목 한정), inception_date(6/17), 근사 방식(오늘 갭 고정 가정) 등은 이번 문서에서 이미 결정해 두었으므로 커서가 별도로 물어볼 필요는 없다.

---

## 9. 한계 및 판단 보류 (명시)

- D2의 "since-inception 기회비용"은 **오늘 시점의 갭이 가동 이후 계속 유지됐다는 단순화 가정**을 쓴다. 실제로는 6/22~7/8 사이 포지션이 조금씩 바뀌었을 것이므로, 이 수치는 **정확한 실현 손익이 아니라 상한선 성격의 근사치**로 취급해야 한다.
- 이 작업이 끝나도 "실제로 손해를 봤다"는 사실 자체가 바뀌거나 복구되지는 않는다. 이 스펙의 목적은 **그 규모를 숫자로 확정하는 것**이지, 손실을 되돌리는 것이 아니다.
- 전체 알파 유니버스(수백 종목) 백필은 이번 범위 밖이며, 필요해지면 별도 스펙(P5-E 등)으로 리스크(rate limit)를 다시 검토한 후 진행 권장.

### 9.1 D1 초기 버그 — `prices_history.csv` 축소 (2026-07-09, 종결: 손실 허용)

| 항목 | 내용 |
|------|------|
| **사건** | D1 초기 구현이 티커마다 `to_csv`로 `prices_history.csv`를 통째 재작성 → 중간 truncate/NUL·행 소실 가능. 이후 **atomic write + 단일 merge**로 수정 완료. |
| **규모** | 원본 ~9,205행 → 현재 ~7,961행 (**~1,243행 소실**). 저장소 내 pre-D1 백업 없음. |
| **소실 성격** | 주로 **2025-04-17·2025-05-17 월간 스냅샷**(현재 0행) 및 희소 장기 모멘텀 기준점. **2026-06-22 이후 일별 데이터는 온전**. |
| **영향 확인** | `python scripts/verify_prices_history_impact.py` — 아침 baseline=`ai_export_bundle` daily_brief, 현재 `prices_history.csv`로 `alpha_gate_diagnostics`/`hakedaka_data_quality` **실제 재생성** 후 비교. 산출: `outputs/prices_history_impact_check.json`. (2026-07-09: `missing_price`/`missing_price_count`/`data_quality_below_60` **변동 없음** → `no_material_change`) |
| **운용 판단** | **완전 재수집 보류**. 오늘 아침 `alpha_report.md` 등은 사고 이전 데이터로 생성 → 소급 영향 없음. D2 산출물(`core_saa_gap_*`)은 `data_trust=untrusted` — 운용 판단에 사용 금지. |
| **향후 복구(선택)** | 필요 시 **날짜 3건(4/17·5/17·6/17) 시장 전체 일괄 조회**가 종목별 반복보다 효율적 — 별도 작업으로 분리. |

