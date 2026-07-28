# 운용 Refresh 가이드 (P4)

> **대상:** 일상 운용자  
> **목적:** 데이터 갱신 → 분석 → 리포트 → 검증 순서를 분리해 안전하게 반복 실행  
> **전제:** 자동매매·증권사 API 없음. 모든 매매는 사람 승인 후 별도 실행.

이 문서는 P1(Target UI 단일화), P2(Alpha v0.2 shadow off), P3(Flow 공통 API) 이후 구조를 반영합니다.

---

## 빠른 참조 — 무엇을 언제 실행하나

| 루틴 | 빈도 | 진입점 | 산출물 핵심 |
|------|------|--------|-------------|
| **일상 분석** | 매 영업일 | UI **② 전체 분석** 또는 `python scripts/daily_pipeline.py` | `daily_report.md`, `ai_export_bundle.json` |
| **수급 refresh** | 매 영업일 (분석에 포함) | 전체 분석 내 Alpha flow refresh + Flow Dashboard | `investor_flows.csv`, `flow_dashboard_summary.json` |
| **Universe bulk** | 주 1회 | `python -m src.data_refresh.pykrx_collect_main` | `universe.csv`, KOSDAQ coverage |
| **Target 변경 후** | 승인 직후 | clean run 1~2회 | `target_guard PASS`, audit log |
| **AI export 검증** | 리포트 공유 전 | acceptance + bundle consistency | `report_clarity_validation.json` |

---

## 1. 일상 실행 루틴

### 1.1 권장 순서 (Streamlit)

```
[1] 대시보드 — 오늘 상태·Step 진행 확인
[2] (필요 시) 데이터 탭 — 시장지표·가격 갱신
[3] 사이드바 → ② 전체 분석 실행
[4] 대시보드 Step ⑦~⑧ / 종합 포트 — Gap·Executable 확인
[5] 알파 → 수급 현황 — Flow Dashboard (review-only)
[6] (필요 시) GPT/외부 검토용 ai_export_bundle 확인
```

### 1.2 CLI (자동화·스케줄러)

```powershell
cd C:\Cursor\multi_asset_trigger_portfolio

# 일일 갱신 + 전체 파이프라인 (권장)
python scripts/daily_pipeline.py --no-backtest

# 분석만 (데이터 이미 갱신된 경우)
python -m src.main --no-backtest
```

`daily_pipeline.py`는 시장지표·Tier H 가격 갱신 후 `run_full_pipeline()`을 호출하고 `daily_run_log.jsonl`에 기록합니다.

### 1.3 분석 후 확인할 산출물

| 확인 항목 | 파일 / 위치 | PASS 기준 (일반) |
|-----------|-------------|------------------|
| **daily_report** | `outputs/daily_report.md` | 파일 생성, Technical/Operational 섹션 존재 |
| **ai_export_bundle** | `outputs/ai_export_bundle.json` | 생성됨, `daily_brief` 포함 |
| **target_guard** | `outputs/system_health.json` → `target_portfolio_guard` | `severity: PASS`, `changed_rows: 0` |
| **Actual Buy Allowed** | `outputs/final_execution_decision.json` | 운용 정책상 기대값과 일치 (현재 환경: `0` 가능) |
| **GREEN Layer** | `outputs/daily_report.md` 또는 아래 스크립트 | Technical/Operational/Market/Full 표 |
| **SAA Restart** | `outputs/saa_restart_readiness_report.json` | `NOT_READY`면 SAA 재개 **금지** |
| **Alpha v2** | `outputs/alpha_v2_summary.json` | shadow mode, coverage·validation_status |
| **Flow Dashboard** | `outputs/flow_dashboard_summary.json` | `fresh_flow_count` / `stale_flow_count` |

### 1.4 점검 스크립트 (분석 직후)

```powershell
# GREEN Layer + SAA Restart + Actual Buy Allowed
python scripts/print_green_layers_status.py

# target_guard · hash · snapshot_alignment
python scripts/print_target_write_audit_status.py
```

### 1.5 AI export 검증

전체 분석 시 `publish_report_exports()`가 `daily_brief.json` + `ai_export_bundle.json`을 생성합니다.

| 검증 | 파일 |
|------|------|
| 리포트 명확성 | `outputs/report_clarity_validation.json` → `pass: true` |
| 번들 정합성 | `outputs/bundle_consistency_validation.json` → `pass: true` |
| Acceptance | `outputs/acceptance_report.json` → AC-08 ai_export |

운용 승인 탭 **운용 승인 검증 (AC)** 또는:

```powershell
python -m src.validation.acceptance_main
```

---

## 2. 수급 refresh 루틴

수급 데이터는 **Alpha v1 Signal Board**와 **Alpha v2 shadow**, **Flow Dashboard**가 공통 API(`src/alpha_flow/`)의 stale 기준을 공유합니다.  
**수급 신호 ≠ 매수 허가** (review-only).

### 2.1 자동 refresh (일상)

전체 분석 시 Alpha pipeline이 Signal Board 대상 ticker에 대해:

1. `data/investor_flows.csv` 갱신 (`src/alpha/flow_refresh.py`)
2. Alpha v2 institutional flow overlay (`alpha_v2_scored.csv`)
3. Flow Dashboard 산출 (`flow_dashboard_summary.json`, leaderboard CSV)

별도 수동 실행 없이 **② 전체 분석** 한 번으로 포함됩니다.

### 2.2 수동·검증

```powershell
# flow refresh 메타 + Signal Board 연동 검증
python scripts/validate_flow_refresh_run.py
```

확인 파일:

| 파일 | 내용 |
|------|------|
| `data/investor_flows.csv` | ticker별 flow_signal, staleness_days, source |
| `data/institutional_flow_krx.csv` | (있으면) v2 전용 KRX flow |
| `outputs/gpt_context.json` | `kr_alpha_meta.flow_refresh` 메타 |
| `outputs/flow_dashboard_summary.json` | fresh/stale count, cache_meta |

### 2.3 fresh / stale count 읽는 법

두 곳의 숫자는 **동일 기준** (`src/alpha_flow/flow_classifier.py`, `staleness_days >= 3` 또는 `flow_signal=STALE`):

| 출처 | 필드 |
|------|------|
| Alpha v2 | `alpha_v2_summary.json` → `coverage.fresh_flow_count`, `stale_flow_count` |
| Flow Dashboard | `flow_dashboard_summary.json` → `fresh_flow_count`, `stale_flow_count`, `cache_meta` |

UI: **알파 → 수급 현황** 탭 상단 카드.

### 2.4 stale 비율이 높을 때

| 상황 | 해석 | 조치 |
|------|------|------|
| `stale_flow_count` ≫ `fresh_flow_count` | PyKRX/KRX 인증 실패, 장 휴장, API 오류 가능 | KRX ID/PW 확인 → 데이터 탭 PyKRX 재수집 → 재분석 |
| `flow_coverage_pct` < 80% | Signal Board 대상 중 갱신 실패 다수 | `validate_flow_refresh_run.py` 경고 확인 |
| cache fallback | `cache_meta.warnings`에 PyKRX miss | **stale warning** — 관찰만, Watch 생성 안 함 |

### 2.5 stale 정책 (P3)

- **Buy Watch / Trim Watch 생성 안 함**
- stale held 종목 → `alpha_v2_flow_stale_warnings.csv` (warning only)
- `flow_confidence: LOW`, `flow_signal_state: stale`
- Actual Buy Allowed=0 / NO_TRADE이면 모든 flow row `buy_permission=false`, `review_only=true`

---

## 3. 주간 universe bulk 루틴

Alpha v2·Flow Dashboard의 KOSDAQ coverage는 `data/universe.csv` 동기화에 의존합니다.

### 3.1 권장 주기

**주 1회** (또는 KOSDAQ 신규 상장·유니버스 불일치 의심 시)

### 3.2 실행

```powershell
# KOSDAQ universe만 동기화 + liquid 가격 bootstrap (KOSPI 유지)
python -m src.data_refresh.pykrx_collect_main --kosdaq-sync-only

# 전체 bulk (universe + prices + fundamentals, liquid scope)
python -m src.data_refresh.pykrx_collect_main --scope liquid
```

UI: **데이터** 탭 → **PyKRX 일괄 수집**

### 3.3 확인

| 항목 | 확인 방법 |
|------|-----------|
| KOSPI + KOSDAQ count | `data/universe.csv` 행 수, `outputs/system_health.json` tier 검증 |
| KOSDAQ universe | bulk 결과 JSON의 `kosdaq_count` (약 1,700+) |
| Alpha v2 scored | `alpha_v2_summary.json` → `coverage.scored_count`, `kosdaq_universe_count` |
| KOSDAQ Shadow Watch | `alpha_v2_summary.json` → `validation_status`, policy notes |

bulk 후 **② 전체 분석** 1회 필수.

---

## 4. Target 변경 후 루틴

Target write는 **승인된 경로만** 허용됩니다. 파이프라인이 CSV를 자동 덮어쓰지 않습니다.

### 4.1 승인 경로 (P1)

```
Streamlit: 알파 → Target 승인  (유일한 UI 승인 버튼)
    → apply_proposed_target()
    → write_operational_target()
    → target_portfolio_guard + target_write_audit

CLI (관리자): scripts/apply_target_draft.py --apply
    → 동일 bridge 경로
```

대시보드 **Step ⑥**은 draft preview·diff만 — **승인 버튼 없음**.

### 4.2 승인 직후 체크리스트

| # | 항목 | 확인 |
|---|------|------|
| 1 | target write audit | `outputs/decision_log.jsonl` → `event: target_write_audit`, `target_write_allowed: true` |
| 2 | target_guard | `severity: PASS` |
| 3 | changed_rows | `0` (승인 직후 run 기준) |
| 4 | proposal_leak | `0` |
| 5 | material | `0` |
| 6 | target_hash | operational = user (`target_hash=user_target_hash`) |
| 7 | snapshot_alignment | `True` |
| 8 | clean run | **1~2회** 연속 분석, hash·guard idempotent |

```powershell
python scripts/print_target_write_audit_status.py

# 2-run idempotency (관리자)
python scripts/verify_production_clean_run.py
```

### 4.3 clean run PASS 조건 (요약)

- `target_guard PASS`
- 이번 run `target_write` **0건** (승인 run 제외)
- `restore_occurred: false`
- `proposal_leak: 0`, `changed_rows: 0`
- `Actual Buy Allowed` · `execution_scope` · `NO_TRADE` — 변경 전과 동일
- `daily_report.md`, `ai_export_bundle.json` 정상 생성

---

## 5. 승인 정책

| 정책 | 내용 |
|------|------|
| **UI 승인 단일화 (P1)** | Streamlit target 승인 버튼 = **알파 → Target 승인** 탭만 |
| **대시보드 Step ⑥** | preview-only — draft 비교·안내, 승인 없음 |
| **CLI** | `scripts/apply_target_draft.py` — 고급/관리자·headless용 |
| **write 우회 금지** | `target_portfolio.csv` 직접 편집·우회 write 금지 (admin script 제외) |
| **blocked reintroductions** | `030190` 등 수동 제거 종목 — `override_previous_removal` 없으면 approval bridge **차단** |
| **audit** | 모든 허용 write → `target_write_audit` + `decision_log.jsonl` |

---

## 6. Shadow 정책

설정: `data/portfolio_policy.yaml` → `alpha_shadow`

```yaml
alpha_shadow:
  v0_2_enabled: false      # Alpha v0.2 shadow — 기본 OFF
  v2_enabled: true         # Alpha v2 shadow — ON
  flow_dashboard_enabled: true
```

| 계층 | 역할 | 매수 허가 |
|------|------|-----------|
| **Alpha v1** | Production — Signal Board, candidates, trade_actions | gate·scope·Actual Buy Allowed 적용 |
| **Alpha v2** | Shadow — flow overlay, Buy/Trim **Watch** | **아니오** — `review_only`, candidate only |
| **Alpha v0.2** | disabled by config — 리포트에 "disabled" 표시 | **아니오** |
| **Flow Dashboard** | 수급 현황 UI + leaderboard | **아니오** — review-only |

v0.2 재활성화: `v0_2_enabled: true` 후 재분석 (코드 삭제 없음).

---

## 7. 상태 해석

### 7.1 자주 혼동되는 표현

| 표시 | 의미 | 흔한 오해 |
|------|------|-----------|
| **Technical GREEN** | 데이터·guard·health 기술적 PASS | ≠ 신규매수 허가 |
| **ETF_ONLY** | execution scope 제한 | ≠ ETF 매수 허가 |
| **Actual Buy Allowed = 0** | 실행 가능 신규매수 **없음** | Watch·shadow 신호도 매수 불가 |
| **NO_TRADE** | 모든 신호 **review-only** | UI·리포트에 명시 |
| **Buy Watch / Trim Watch** | Alpha v2 shadow 관찰 신호 | buy permission 아님 |
| **SAA Restart NOT_READY** | Core SAA 단계적 재개 **금지** | `saa_restart_readiness_report.json` 참조 |

### 7.2 GREEN Layer (4계층)

| Layer | 대표 의미 |
|-------|-----------|
| Technical | system_health, target_guard, data gate |
| Operational | acceptance, dry-run, Actual Buy Allowed |
| Market | policy_cap, KOSPI/USD watch |
| Full | 종합 (Technical + Operational + Market) |

`python scripts/print_green_layers_status.py`로 한 번에 출력.

### 7.3 Flow stale vs Buy permission

```
stale flow → LOW confidence warning only
Actual Buy Allowed=0 → buy_permission=false (모든 flow row)
NO_TRADE → review_only=true
```

---

## 8. 일일·주간 점검표

분석 완료 후 아래를 순서대로 확인합니다. `( )`에 PASS/FAIL/값 기록.

### 8.1 Core (매일)

- [ ] **target_guard** — `PASS`, `changed_rows=0`, `proposal_leak=0`
- [ ] **health_overall** — `system_health.json` → `overall: pass` (fail=0)
- [ ] **acceptance_overall** — `YELLOW`/`GREEN` 등 기대 운용 상태
- [ ] **execution_scope** — e.g. `ETF_ONLY` (의도와 일치)
- [ ] **Actual Buy Allowed** — `final_execution_decision.json`
- [ ] **NO_TRADE** — scope·플래그 확인
- [ ] **daily_report** — `outputs/daily_report.md` 생성
- [ ] **ai_export_bundle** — `outputs/ai_export_bundle.json` 생성

### 8.2 Flow (매일)

- [ ] **fresh_flow_count** — `flow_dashboard_summary.json` / `alpha_v2_summary.json`
- [ ] **stale_flow_count** — v2와 dashboard **동일 값**
- [ ] **stale 비율** — 높으면 §2.4 조치
- [ ] **Buy Watch count** — stale 제외된 fresh watch만
- [ ] **Trim Watch count** — held/target trim vs informational 구분

### 8.3 Alpha (매일·리서치)

- [ ] **Alpha v1** — `alpha_candidates.csv`, `alpha_signal_board.csv`
- [ ] **Alpha v2 final candidates** — `alpha_v2_final_candidates.csv` (max 8)
- [ ] **Alpha v0.2** — disabled (brief/bundle에 `alpha_v0_2_status: disabled`)

### 8.4 Validation (리포트 공유·승인 전)

- [ ] **report_clarity_validation** — `pass: true`
- [ ] **bundle_consistency_validation** — `pass: true`, `snapshot_alignment: true`
- [ ] **target_hash** — acceptance = health = daily_report 일치

### 8.5 주간 추가

- [ ] **universe.csv** — KOSPI+KOSDAQ sync
- [ ] **KOSDAQ count** — bulk 결과 vs `alpha_v2_summary.coverage`
- [ ] **tier_b_refresh** — `outputs/tier_b_refresh.json` 주간 갱신 상태

### 8.6 Target 변경 시에만

- [ ] **target_write_audit** — 승인 run 1건, guard PASS after write
- [ ] **clean run 1~2회** — §4.3
- [ ] **030190 absent** — blocked ticker 미재유입

---

## 부록 A — 주요 출력 파일 맵

| 경로 | 용도 |
|------|------|
| `outputs/daily_report.md` | 사람용 일일 리포트 |
| `outputs/daily_brief.json` | GPT/AI 입력 요약 |
| `outputs/ai_export_bundle.json` | 교차 검증 통합 번들 |
| `outputs/final_execution_decision.json` | 최종 운용 권위 |
| `outputs/acceptance_report.json` | AC 검증 |
| `outputs/system_health.json` | health + target_guard |
| `outputs/alpha_v2_summary.json` | Alpha v2 shadow 요약 |
| `outputs/flow_dashboard_summary.json` | Flow Dashboard 메타 |
| `outputs/saa_restart_readiness_report.json` | SAA 재개 준비 |
| `outputs/decision_log.jsonl` | target write · shadow skip 등 이벤트 |
| `data/investor_flows.csv` | v1/v2 공통 flow 원천 |
| `data/portfolio_policy.yaml` | alpha_shadow 플래그 |

## 부록 B — 관련 문서

| 문서 | 내용 |
|------|------|
| [USER_GUIDE.md](USER_GUIDE.md) | UI·bat·일반 운용 |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | AC 상세 |
| [OPS_POLICY_v1.0.2.md](OPS_POLICY_v1.0.2.md) | 운용 정책 |
| [DRY_RUN_LOG_SCHEMA.md](DRY_RUN_LOG_SCHEMA.md) | dry-run 로그 |

---

*문서 버전: P4 · Alpha v0.2 default off · Target UI 단일화 · Flow 공통 API 반영*
