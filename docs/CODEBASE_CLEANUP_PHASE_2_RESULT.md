# Cleanup Phase 2 — `alpha_v2` + `alpha_flow` archive

> SPEC: [`CODEBASE_CLEANUP_PHASE_0_1_2_SPEC.md`](CODEBASE_CLEANUP_PHASE_0_1_2_SPEC.md)  
> 원칙: **삭제 아님 · git mv · `ENABLE_ALPHA_V2=False` 기본**. kr_alpha 코어·익절엔진·`src/alpha/` 비즈니스 로직 미변경(import만 게이트로 전환).

## 1. 이동 목록

| 원본 | archive | 개수 |
|------|---------|------|
| `src/alpha_v2/` | `archive/20260715_alpha_v2/` | 17 `.py` |
| `src/alpha_flow/` | `archive/20260715_alpha_flow/` | 9 `.py` |
| 관련 테스트 (`test_alpha_v2*`, `test_flow_*` 일부, `test_shadow_flow_cache`, `test_run_mode*`) | `archive/20260715_tests/` | +9 |

## 2. 잔여 참조 처리

신규 [`src/alpha_v2_gate.py`](../src/alpha_v2_gate.py):
- `ENABLE_ALPHA_V2=False` (환경변수 `ENABLE_ALPHA_V2=1`로 복구 가능 — 패키지를 `src/`로 되돌린 뒤)
- 스텁: price fetch skip=False(`alpha_v2_disabled`) · snapshot no-op · report/flow 섹션에 disabled 문구 · `get_flow_for_ticker_unified`→legacy investor_flows · stale classifier 로컬 유지(`flow_refresh`/`signal_board`)
- 호출부: `alpha_pipeline`, `full_pipeline`, `pipeline_runner`, `run_mode_contract`, `run_hooks`, `report_writer`, `ai_export`, `alpha_signal_board`, `flow_refresh`, `history_ledger`, `flow_status_panel`, `alpha_shadow_policy`
- shadow: `alpha_v2_shadow_skipped` / `flow_dashboard_skipped` reason=`module_unavailable` (v0.2과 동일 패턴)

## 3. 검증

| 항목 | 결과 |
|------|------|
| `import src.main` | ok |
| `alpha_v2_enabled()` | False |
| `tests/test_alpha_v2_gate.py` + shadow/flow_refresh | pass |
| `src/alpha_v2` / `src/alpha_flow` | 원위치 없음 |
| **전체 파이프라인** (`python -m src.main`, 2026-07-15) | **exit 0** · Data Gate GREEN · Actual Buy Allowed=0 · Health warn(1) |
| `decision_log.jsonl` | `run_id=2026-07-15T20:52:52+09:00` — `alpha_v2_shadow_skipped`/`flow_dashboard_skipped`(`module_unavailable`)→`bundle_reconciliation` |
| `daily_report.md` | Alpha v2 / 수급 섹션 헤더 + `ENABLE_ALPHA_V2=False / archived` 문구 |

**종결 (2026-07-15):** 원장 독립 검증 완료 — archive 개수·커밋 `548effa`·게이트 패턴·decision_log·daily_report disabled 문구 일치. **2단계 종료.**

**원장 보완 메모 (비차단):**
- `daily_report.md` ~428행 근처 `Alpha v2 shadow history updated: yes` — disabled 상태와 어긋날 수 있는 잔여 문구. 사소·후순위 청소.
- pytest 미확인 2건 원장 조사: `test_run_mode_contract_pass_if_present`는 현재 `run_mode_contract_validation.json`(contract_pass=true, pykrx=0)로 통과 예상(당시 stale 가능); `test_refresh_preserves_on_api_failure`는 tier2 FRED/KOSIS로 alpha_v2/flow와 무관·`external_data_dependency` 선재 부채. **phase 2 회귀 아님** — 전체 18건 재실행 불필요.

