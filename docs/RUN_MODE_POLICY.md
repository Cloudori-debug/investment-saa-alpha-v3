# Run Mode 운영 정책 (P4c)

> **전제:** P0~P3d까지 standard cache-hit 운영 모드가 성립한 이후의 고정 정책입니다.  
> **변경 금지 영역:** gate threshold, policy cap, target write, approval_bridge, Actual Buy Allowed 계산 로직.

---

## 모드 요약

| 모드 | 용도 | refresh 원칙 | network / PyKRX |
|------|------|--------------|-----------------|
| `quick` | 즉시 상태 점검 | cache-only, 최소 산출 | **금지** |
| `standard` | **일일 운영 점검** (기본) | cache-first, incremental | 반복 fetch **금지** |
| `deep` | 주간 정밀 갱신 | full refresh **허용** | 필요 시 허용 |
| `bundle_only` | AI 검증·공유용 | verify-only, **재계산 금지** | **금지** |

---

## quick

**목적:** 대시보드·CLI에서 “지금 상태가 정상인지” 빠르게 확인.

| 항목 | 정책 |
|------|------|
| 허용 refresh | 없음 (기존 `outputs/` 재사용) |
| 금지 refresh | tier 가격, PyKRX, KOSIS, alpha_v2 full, flow full, diagnostics recompute |
| PyKRX | 0 — network fetch 금지 |
| cache miss 시 | 기존 산출물 verify-only. 없으면 skip + 경고 |
| 산출물 | `final_execution_decision.json` 등 core safety 파일은 **읽기·검증만** |

---

## standard (일일 운영)

**목적:** 매 영업일 cache-hit 기준 **~60–120초** 내 일일 분석·리포트·검증.

| 항목 | 정책 |
|------|------|
| 허용 refresh | `final_decision_core` (항상), gate/health 검증, cache miss 시에만 해당 step recompute |
| cache-first step | alpha_v2, shadow flow, tier prices(check-only), diagnostics subset, KOSIS skip, bundle reconcile, post_decision_artifacts, research_outputs, shadow_history, report_exports |
| PyKRX | **0** — `run_mode_contract_validation.json`에서 `contract_pass=true` 필수 |
| cache miss 시 | dependency hash 변경 또는 required output 누락 step만 recompute. profiler·manifest에 reason 기록 |
| 금지 | approval_bridge 연결, target_write, gate threshold 완화, stale cache → buy permission 연결 |

### standard cache-hit 기준선 (P4a)

`outputs/standard_cache_hit_baseline.json` 및 `outputs/baselines/` 참조.

| 항목 | 목표 |
|------|------|
| `total_seconds` | 60~120s |
| `diagnostics` | 0~5s |
| `report_exports` | 0~2s |
| `pykrx_call_count` | 0 |
| `contract_pass` | true |
| `target_write_count` | 0 |
| `actual_buy_allowed` | 운용 정책 기준 (현재: **0**) |

---

## deep

**목적:** 주 1회 등 **정밀 갱신** — full refresh 허용.

| 항목 | 정책 |
|------|------|
| 허용 refresh | alpha_v2 full, flow full, shadow outcome full rebuild, diagnostics force recompute |
| PyKRX | 필요 시 허용 (단, 운용 판단·gate 변경 없음) |
| cache | 동일 hash면 reuse 가능 — manifest에 `deep_cache_reuse` reason 기록 |
| 금지 | target_write, approval_bridge, policy cap 변경 |

---

## bundle_only

**목적:** AI export·bundle 공유 전 **verify-only** 패스.

| 항목 | 정책 |
|------|------|
| 허용 | 기존 산출물 존재·정합성 검증, clarity/sync export |
| 금지 | **모든 recompute** (research, shadow append, report rebuild, network) |
| cache miss 시 | `outputs_missing` blocker — 재계산하지 않고 fail-soft 기록 |

---

## PyKRX call 정책

```text
standard / quick / bundle_only  → pykrx_call_count = 0 (contract enforced)
deep                            → 필요 시만, profiler 기록
```

`outputs/run_mode_contract_validation.json`의 `contract_pass`가 standard 일일 운영의 **필수 PASS 조건**입니다.

---

## cache miss 시 행동

1. **profiler** (`runtime_profile.json`) 및 step manifest에서 `skip_reason` / `blockers` 확인
2. **의도된 miss** (입력 변경, deep mode, 첫 run) → 해당 step만 recompute, 전체 full refresh 금지
3. **비의도 miss** (price hash drift, manifest 누락) → P1.6e 이후 playbook: price hash → alpha_v2 → flow 순 점검
4. **절대 금지:** stale cache hit을 Actual Buy Allowed 상승으로 연결

---

## 안전 문구 (운용 판단 — 변경 금지)

```text
Actual Buy Allowed = 0  →  신규매수 없음
ETF_ONLY              ≠  ETF 매수 허가
Watch Signal          ≠  Actual Buy Allowed
GREEN Layer           ≠  매수 명령
```

- `execution_scope: ETF_ONLY`는 **표시·범위 라벨**이며, Actual Buy Allowed가 0이면 executable buy 없음.
- authoritative scope는 `NO_TRADE` 등 별도 필드로 daily_report·acceptance에 정렬.

---

## 관련 문서·산출물

| 문서/파일 | 내용 |
|-----------|------|
| `docs/OPERATIONS_REFRESH_GUIDE.md` | 일상 refresh 루틴·산출물 확인 |
| `outputs/standard_cache_hit_baseline.json` | P4a baseline 요약 |
| `outputs/baselines/` | baseline raw profile/steps/contract |
| `outputs/run_mode_contract_validation.json` | standard contract PASS/FAIL |

---

## CLI 예시

```powershell
cd C:\Cursor\multi_asset_trigger_portfolio

python -m src.main --run-mode quick
python -m src.main --run-mode standard      # 일일 운영 (기본)
python -m src.main --run-mode deep
python -m src.main --run-mode bundle_only
```
