# Dry-run Log Schema v1.0

> **목적:** 실매매 없이 10~20영업일 신호 품질 관찰  
> **파일:** `outputs/dry_run_log.jsonl` (1 run = 1 JSON line)  
> **관련:** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) AC-09

---

## 1. 기록 시점

매 영업일 **전체 분석 실행** (`run_full_pipeline`) 직후 자동 append.  
동일 `date`에 여러 run 가능 — `run_id`로 구분.

---

## 2. 필드 스키마

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `schema_version` | string | ✅ | `"1.0"` |
| `run_id` | string | ✅ | ISO8601 로컬 시각, 예 `2026-06-19T21:30:00+09:00` |
| `generated_at` | string | ✅ | 파이프라인 완료 시각 (ISO) |
| `date` | string | ✅ | `market_indicators.date` (as_of) |
| `overall_status` | string | ✅ | GREEN / YELLOW / RED (AC) |
| `execution_scope` | string | ✅ | NO_TRADE / ETF_ONLY / ETF_AND_BETA / FULL_WITH_ALPHA |
| `alpha_approval` | string | ✅ | APPROVED / RESTRICTED / BLOCKED |
| `data_gate` | string | ✅ | unified (effective) gate |
| `portfolio_gate` | string | ✅ | |
| `alpha_gate` | string | ⬜ | |
| `applied_regime` | string | ⬜ | |
| `computed_regime` | string | ⬜ | |
| `override_active` | bool | ✅ | |
| `override_age_days` | int | ⬜ | set_date → date |
| `action_count` | int | ✅ | trade_actions 건수 |
| `alpha_candidates` | int | ✅ | |
| `triggers_active` | string[] | ✅ | ACTIVE trigger keys |
| `buy_allowed_count` | int | ⬜ | Buy-allowed 액션 수 |
| `kr_alpha_wait_count` | int | ⬜ | kr_alpha Wait (YELLOW block) |
| `market_stale_max_days` | int | ⬜ | provenance 최대 stale |
| `notes` | string | ⬜ | 운용자 메모 (수동 append 시) |

---

## 3. Execution Scope 정의

| Scope | 의미 |
|-------|------|
| `NO_TRADE` | Critical FAIL 또는 portfolio/unified RED |
| `ETF_ONLY` | Core OK, Alpha 제한 — **cash_short_bond·ETF·자산군 Gap 검토만** |
| `ETF_AND_BETA` | domestic/global beta trigger 충족 시 추가매수 **검토** 가능 |
| `FULL_WITH_ALPHA` | Alpha APPROVED + GREEN — kr_alpha도 **사람 승인 후** 검토 |

**자동매매는 모든 scope에서 금지.**

---

## 4. 관찰 체크리스트 (dry-run 기간)

매일 또는 주 1회 검토:

- [ ] regime / override 변화가 시장과 맞는가
- [ ] 불필요한 Buy-allowed 폭증 없었는가
- [ ] data_gate YELLOW 시 kr_alpha Wait가 적용됐는가
- [ ] trigger stale 시 해당 trigger 비활성됐는가
- [ ] Alpha gate와 execution_scope 일치하는가

---

## 5. 예시 레코드

```json
{
  "schema_version": "1.0",
  "run_id": "2026-06-19T09:15:00+09:00",
  "generated_at": "2026-06-19T09:15:02+09:00",
  "date": "2026-06-17",
  "overall_status": "YELLOW",
  "execution_scope": "ETF_ONLY",
  "alpha_approval": "RESTRICTED",
  "data_gate": "YELLOW",
  "portfolio_gate": "GREEN",
  "alpha_gate": "YELLOW",
  "applied_regime": "YELLOW_STABLE",
  "computed_regime": "RISK_ON",
  "override_active": true,
  "action_count": 21,
  "alpha_candidates": 8,
  "triggers_active": ["kospi_pullback"],
  "buy_allowed_count": 0,
  "kr_alpha_wait_count": 3,
  "market_stale_max_days": 0
}
```

---

## 6. GREEN 승격에 필요한 dry-run

- **≥10 서로 다른 `date`** (영업일)
- Critical AC FAIL 0
- `execution_scope`가 NO_TRADE인 날이 연속 3일 미만
- 운용자 sign-off (문서/이슈 트래커)

---

## 7. run_manifest.json

동일 run의 산출물 묶음 — AC-08 AI export 검증용.

**경로:** `outputs/run_manifest.json`

```json
{
  "run_id": "2026-06-19T09:15:00+09:00",
  "generated_at": "2026-06-19T09:15:02+09:00",
  "as_of": "2026-06-17",
  "source_outputs": [
    "compass_regime.json",
    "system_health.json",
    "acceptance_report.json",
    "trade_actions.csv",
    "gpt_context.json"
  ]
}
```

`ai_export_bundle.json`의 `run_id`가 `run_manifest.run_id`와 일치하면 AC-08 **PASS**.
