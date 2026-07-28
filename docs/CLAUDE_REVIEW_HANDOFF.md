# Claude 검토·검증 핸드오프

> **프로젝트:** Multi-Asset Trigger Portfolio v2.0  
> **경로:** `C:\Cursor\multi_asset_trigger_portfolio`  
> **최종 판정일:** 2026-07-08  
> **개발 상태:** `complete` — 운용 보조 도구로 사용 가능

이 문서는 **클로드(또는 외부 검토자)** 가 저장소를 열고 개발 완료 여부·안전성·리포트 정합성을 **독립적으로 검증**할 수 있도록 작성되었습니다.

---

## 0. 빠른 검증 (권장 첫 단계)

저장소 루트에서 아래를 실행하세요.

```powershell
cd C:\Cursor\multi_asset_trigger_portfolio
python scripts/verify_claude_review.py
```

**결과 파일:** `outputs/claude_verification_report.json`

| 필드 | 의미 |
|------|------|
| `overall_pass` | blocking 체크 전부 통과 여부 |
| `blocking_failures` | 운용 차단급 미충족 항목 ID |
| `non_blocking_failures` | 참고용 (baseline 미갱신, warmup contract 등) |
| `files_to_read_for_deep_review` | 심층 검토 시 읽을 파일 목록 |

`overall_pass=true` 이면 **개발 완료 acceptance 기준 충족**으로 판단할 수 있습니다.

### 전체 재검증 (선택)

캐시·산출물이 오래되었거나 `contract_pass=false`(warmup)인 경우:

```powershell
python -m src.main --run-mode quick
python -m src.main --run-mode standard
python -m src.main --run-mode standard
scripts/test_smoke.ps1
python scripts/generate_final_acceptance.py
python scripts/verify_claude_review.py
```

> **참고:** `standard`를 **연속 2회** 실행해야 cache-hit baseline 조건(`pykrx=0`)이 성립합니다.  
> 첫 실행(warmup) 후 `outputs/run_mode_contract_validation.json`의 `contract_pass=false`는 정상일 수 있습니다.

---

## 1. 프로젝트 한 줄 요약

**규칙 기반 자산군 나침반 + SAA/TAA + 종목 분해 + 실행 보조 + 백테스트** 시스템.

- 자동매매·증권사 API **없음**
- 목표: 일관된 배분 의사결정 자동화 + 일일 운용 리포트
- UI: Streamlit (`app.py`, `투자나침반.bat`)
- CLI: `python -m src.main --run-mode {quick|standard|deep|bundle_only}`

---

## 2. 최종 Acceptance 스냅샷

**파일:** `outputs/final_acceptance_summary.json`

```json
{
  "development_status": "complete",
  "operation_ready": true,
  "actual_buy_allowed": 0,
  "target_write_count": 0,
  "contract_pass": true,
  "report_clarity_pass": true,
  "operation_blocking_failures": [],
  "test_smoke": { "passed": 119, "failed": 0 },
  "test_fast": { "passed": 692, "failed": 0 }
}
```

**성능 기준선 (standard cache-hit)**

| 모드 | 시간 | contract | pykrx |
|------|------|----------|-------|
| quick | ~1.7s | quick_contract_pass=true | 0 |
| standard warmup | ~113s | (첫 실행) | 가변 |
| standard cache-hit | ~97s | contract_pass=true | **0** |

**관련 산출물**

| 파일 | 용도 |
|------|------|
| `outputs/final_acceptance_summary.json` | 최종 acceptance 판정 |
| `outputs/FINAL_DEVELOPMENT_COMPLETION_REPORT.md` | 완료 리포트 (사람용) |
| `outputs/report_clarity_validation.json` | P4e clarity 검증 |
| `outputs/quick_mode_validation.json` | quick mode contract |
| `outputs/run_mode_contract_validation.json` | **마지막** standard 실행 contract |
| `outputs/baselines/runtime_profile_standard_final_cache_hit.json` | cache-hit 성능 baseline |
| `outputs/claude_verification_report.json` | 자동 검증 리포트 |

---

## 3. 절대 변경 금지 영역 (운용 불변식)

개발·최적화 과정에서 **의도적으로 고정**된 영역입니다.

| 영역 | 현재 상태 | 검증 방법 |
|------|-----------|-----------|
| Actual Buy Allowed | **0** | `report_clarity_validation.json` → `metrics.actual_buy_allowed_count` |
| target_write | **0** | `final_acceptance_summary.json` → `target_write_count` |
| approval_bridge | 연결 차단 | 코드: `src/runtime/final_decision_core.py` 등 |
| gate threshold | 변경 없음 | diff에서 threshold 상수 미변경 확인 |
| policy cap | 변경 없음 | `final_execution_decision.json` |
| ETF_ONLY | display scope — **매수 허가 아님** | `daily_report.md` 상단 disclaimer |
| NO_TRADE | authoritative scope | `daily_brief.json` → `system_status` |

### 운용 판단 3줄 (고정)

1. `Actual Buy Allowed=0` → **신규매수 없음**
2. `ETF_ONLY` ≠ ETF 매수 허가
3. `NO_TRADE`가 authoritative이면 **실제 실행은 NO_TRADE**

---

## 4. 개발 단계 요약 (P0 → P4e)

### P0~P3: 파이프라인·안전성·cache
- run mode contract (standard cache-first)
- alpha_v2 / shadow flow / tier price cache reuse
- diagnostics / post_decision / research / shadow_history cache
- final_decision_core 항상 실행
- target_guard, approval_bridge, policy cap

### P3d — Report/Export Hash Skip
- `src/runtime/report_export_cache.py`
- report_exports cache-hit (~0.7–0.9s)
- clarity validation은 cache 밖에서 **항상** 실행

### P4a — Standard Baseline Freeze
- consecutive cache-hit baseline 저장 (`outputs/baselines/`)

### P4b — Legacy Test Backlog
- `docs/TEST_BACKLOG.md` — 33건 non-blocking

### P4c — Test Tiering
- smoke / fast / integration / deep
- `scripts/test_smoke.ps1`, `test_fast.ps1`

### P4d — Quick Mode
- `src/runtime/quick_mode_validation.py`
- ~1.7s, cache-only, pykrx=0

### P4e — Report Clarity Scope Alignment (마지막 필수 패치)

**문제:** `ETF_ONLY`(display) vs `NO_TRADE`(authoritative) 표기 불일치 → `report_clarity_pass=false`

**해결:** 매수 로직 변경 없이 **보고서 문구/표시 정렬**

| scope | 역할 | 사용자 표시 |
|-------|------|-------------|
| authoritative | 실제 실행 권한 | `NO_TRADE — 신규매수 없음` |
| display | 정책/기술 보조 | `ETF_ONLY — ETF 매수 허가가 아님` |
| execution permission | 실행 허가 | `NO_TRADE` |
| Actual Buy Allowed | 최종 판단 | `0` |

**핵심 수정 파일**

| 파일 | 변경 |
|------|------|
| `src/report/authoritative_status.py` | dual-scope 필드, sync 함수 |
| `src/report/execution_metrics.py` | `validate_report_clarity()` |
| `src/report/export_daily_brief.py` | brief/report scope 문구 |
| `src/report/publish.py` | acceptance sync |
| `src/runtime/pipeline_runner.py` | quick mode clarity revalidate |
| `tests/test_report_clarity_scope.py` | P4e 단위 테스트 |

**검증 기대값 (`outputs/report_clarity_validation.json`)**

```json
{
  "pass": true,
  "authority_preview": [
    "Authoritative scope: NO_TRADE — 신규매수 없음",
    "Policy/display scope: ETF_ONLY — ETF_ONLY는 ETF 매수 허가가 아님",
    "Execution permission: NO_TRADE"
  ]
}
```

---

## 5. Run Mode 운영 정책

**문서:** `docs/RUN_MODE_POLICY.md`

| 모드 | 용도 | network/PyKRX | 권장 주기 |
|------|------|---------------|-----------|
| `quick` | 즉시 상태 점검 | **금지** | 수시 |
| `standard` | **일일 운영 리포트** | cache-hit 시 **0** | 매 영업일 |
| `deep` | 정밀 갱신 | 필요 시 허용 | 주 1회 (수동) |
| `bundle_only` | AI 검증·공유 | verify-only | 필요 시 |

---

## 6. 아키텍처 (검토용)

```
CLI/UI
  └─ src.main (--run-mode)
       └─ pipeline_runner.py
            ├─ final_decision_core (항상)
            ├─ cache steps (alpha_v2, shadow, diagnostics, research, report_exports…)
            ├─ publish / export_daily_brief
            └─ report_clarity_validation (항상, cache 밖)

안전성 계층
  ├─ gate / policy_cap / target_guard
  ├─ approval_bridge (target_write 차단)
  └─ authoritative_status (NO_TRADE vs ETF_ONLY 분리)
```

**dual-scope 설계 의도**
- `acceptance_report.execution_scope` 상단 `ETF_ONLY` = display/policy
- `daily_brief` authoritative = `NO_TRADE`
- 불일치 가능. **설명 필드 존재 시 clarity pass**

---

## 7. 테스트 현황

| tier | 결과 | 스크립트 |
|------|------|----------|
| smoke | 119 / 0 | `scripts/test_smoke.ps1` |
| fast | 692 / 0 | `scripts/test_fast.ps1` |
| integration/deep | 수동 | `scripts/test_integration.ps1`, `test_deep.ps1` |

**legacy backlog:** 33건 (`docs/TEST_BACKLOG.md`) — **non-blocking**

---

## 8. 클로드 검토 체크리스트

### A. 안전성 (blocking)
- [ ] `actual_buy_allowed_count == 0`
- [ ] `target_write_count == 0`
- [ ] gate/policy_cap/threshold 코드 diff에 완화 없음
- [ ] cache-hit이 buy permission과 연결되지 않음

### B. Report Clarity — P4e (blocking)
- [ ] `report_clarity_validation.json` → `pass: true`
- [ ] `daily_report.md` 상단에 authoritative `NO_TRADE — 신규매수 없음`
- [ ] `ETF_ONLY는 ETF 매수 허가가 아님` disclaimer 존재
- [ ] `Actual Buy Allowed: 0` 명시

### C. Run Mode Contract
- [ ] quick: `pykrx_call_count=0`, `network_refresh_executed=false`
- [ ] standard cache-hit baseline: `pykrx_call_count=0` (`baselines/runtime_profile_standard_final_cache_hit.json`)
- [ ] 마지막 run이 warmup이면 `contract_pass=false` 가능 — baseline과 구분

### D. Cache 정합성
- [ ] `report_clarity_validation`이 export cache에 묶이지 않음
- [ ] acceptance ↔ export hash 순환 없음 (P3d)

### E. 테스트
- [ ] smoke 0 failures
- [ ] fast 0 failures (backlog 제외)
- [ ] legacy 33건이 operation blocking 아님

---

## 9. 심층 검토 시 읽을 파일 (우선순위)

1. `outputs/claude_verification_report.json` — 자동 검증 결과
2. `outputs/final_acceptance_summary.json`
3. `outputs/report_clarity_validation.json`
4. `outputs/daily_report.md` (상단 30줄)
5. `outputs/daily_brief.json` → `system_status`
6. `src/report/authoritative_status.py`
7. `src/report/execution_metrics.py` → `validate_report_clarity()`
8. `docs/RUN_MODE_POLICY.md`
9. `docs/TEST_BACKLOG.md`
10. `tests/test_report_clarity_scope.py`

---

## 10. 클로드에게 붙여넣을 검토 프롬프트

```text
Multi-Asset Trigger Portfolio 개발 완료 검토를 요청합니다.

저장소: C:\Cursor\multi_asset_trigger_portfolio

1) 먼저 실행 (또는 결과 파일 읽기):
   python scripts/verify_claude_review.py
   → outputs/claude_verification_report.json 확인

2) 핸드오프 문서 읽기:
   docs/CLAUDE_REVIEW_HANDOFF.md

3) 검토 관점:
   - 안전성: Actual Buy Allowed=0, target_write=0, gate/policy cap 불변
   - P4e: ETF_ONLY(display) vs NO_TRADE(authoritative) — 사용자 오해 방지
   - run mode: standard cache-hit pykrx=0 vs warmup contract 구분
   - cache: report_export cache와 clarity validation 분리
   - 테스트: smoke/fast 0 failures, legacy backlog 33건 non-blocking 타당성

4) 결과 형식:
   - 전체 판정: accept / accept_with_notes / reject
   - blocking 이슈 (있으면 파일·라인 근거)
   - non-blocking 개선 제안
   - 운용 시작 전 체크리스트 3~5개
```

---

## 11. 최종 운영 방침

| 모드 | 용도 |
|------|------|
| `quick` | 즉시 상태 점검 |
| `standard` | 매일 운영 리포트 |
| `deep` | 주간 정밀 갱신 (수동) |
| `bundle_only` | GPT/Claude 검증 공유용 |

**이후:** 새 기능 중단 → standard daily + deep 주간 + backlog 순차 정리

---

## 12. 변경 이력 (검토 앵커)

| 단계 | 완료일 | 핵심 산출물 |
|------|--------|-------------|
| P3d | 2026-07-07 | report_export_cache |
| P4a | 2026-07-07 | standard baseline |
| P4b | 2026-07-08 | TEST_BACKLOG.md |
| P4c | 2026-07-08 | test tiering |
| P4d | 2026-07-08 | quick_mode_validation |
| P4e | 2026-07-08 | report_clarity_pass=true, development_status=complete |
| Claude handoff | 2026-07-08 | 이 문서 + verify_claude_review.py |
