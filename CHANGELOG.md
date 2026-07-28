# Changelog

All notable changes to **Multi-Asset Trigger Portfolio** are documented here.

## [alpha-signal-board] — 2026-06-19

### Added
- **`outputs/alpha_signal_board.csv`** — 종목별 `action_state` (Watch/Buy-ready/Buy-allowed/Hold/Trim/Exit)
- **`grade` ≠ `action_state`** — 5축 신호(fundamental/valuation/volume/price/catalyst) + `missing_for_buy` / triggers
- **`src/alpha/sector_mapping.py`** — name inference + `data/krx_sector_mapping.csv` 템플릿
- **`target_portfolio_proposal.csv`**, **`user_target_portfolio.csv`**, **`target_diff_review.csv`**
- **`alpha_report.md`** — Signal Board 우선, proposal은 `theoretical — watch_only`

### Notes
- Scoring logic unchanged · `data/target_portfolio.csv` auto-overwrite 금지 유지

---

## [v1.0.3-fail-soft-validation] — 2026-06-19

### Added
- **Fail-Soft Validation Patch** — Core ETF vs Alpha permission separation
- **`core_etf_permission`**, **`alpha_auto_buy_permission`**, **`alpha_research_permission`** in reports
- **Candidate sector coverage gate** — alpha auto-buy blocked when shortlist unknown >30% or top10 100%
- **`outputs/validation_findings.json`**, **`data/manual_override_ledger.csv`**

### Notes
- Scoring · target auto-overwrite · auto-trading **unchanged**

---

## [alpha-performance-dashboard-3a] — 2026-06-19

### Added
- **`src/alpha/performance_dashboard.py`** — Core SAA vs Actual vs gate opportunity cost (shadow)
- **`outputs/alpha_performance_dashboard.json|.csv`**
- **`outputs/alpha_gate_opportunity_cost.csv`**, **`alpha_grade_forward_return.csv`**
- **`daily_report`** — SAA-relative Alpha Dashboard (shadow only) 섹션

### Notes
- 성공 기준 = **SAA 대비 초과수익 검증** (90일 CSV 누적)
- target / trade_actions / execution_scope **변경 없음**

---

## [core-saa-v0.2-shadow-weights] — 2026-06-19

### Added
- **`core_saa_reference.yaml` v0.2** — 14-slot `target_weight_pct`, `affects_*: false`, USD short bond unresolved
- **Loader validation** — status/authority/affects_* reject; weight sum & unresolved ticker warn
- **Gap diagnostic** — `core_target_weight_pct`, `current_weight_pct`, `gap_pct`, `diagnostic_only`
- **`daily_report`** — mandatory Core reference-only disclaimer (English)

### Notes
- `target_portfolio.csv` · `saa_profiles.yaml` · trade_actions · execution_scope **변경 없음**

---

## [core-satellite-ops-policy] — 2026-06-19

### Added
- **`docs/OPS_POLICY_v1.0.2.md`** — Core / Satellite / Shadow 권한 경계, GREEN 정의, 90일 target 동결
- **`data/core_saa_reference.yaml`** — 장기 ETF-only Core 13종 (`shadow_reference_only`, `authority: none`)
- **`src/exposure/core_saa_reference.py`** — look-through shadow 진단 (`core_saa_reference_diagnostic.json`)
- **`daily_brief.json` / `daily_report.md`** — Core reference shadow 섹션

### Notes
- `target_portfolio.csv` · `saa_profiles.yaml` **변경 없음**
- Core reference는 v1.0.2 execution authority에 **영향 없음**

---

## [report-export-consolidation] — 2026-06-19

### Changed
- **`src/report/publish.py`** — `publish_report_exports()` / `patch_acceptance_and_sync_exports()` 단일 출구
- **`full_pipeline.py`** — `build_ai_export_bundle` 3회 호출 → 1회 + AC-08 메타 동기화
- **`ai_export_bundle.json`** — `daily_brief` 필드 포함, `tables_summary` slim 모드
- **`daily_report.md`** — shadow/alpha/duration 섹션 → `daily_brief` 기반 `build_daily_report_v2_sections()`
- **`src/report/io_utils.py`** — JSON 읽기 공통화

### Notes
- GPT Report v2.0 입력 = **`daily_brief.json` 우선**, bundle = 교차검증·원본용

---

## [report-v2-daily-brief] — 2026-06-19

### Added
- **`src/report/export_daily_brief.py`** — `export_daily_brief()` GPT Report v2.0 경량 입력
- **`outputs/daily_brief.json`** — 파이프라인 마지막 단계 생성 (실행 로직 변경 없음)

---

### Added (shadow mode — v1.0.2 execution unchanged)
- **`src/decision/shadow_diagnostic.py`** — blocked_by, reviewable/theoretical/actual amounts, drawdown ladder 진단
- **`src/decision/shadow_performance.py`** — primary_blocker, SAA proxy MTD, missed_buy 사후 보강, blocked_decision_outcome
- **`outputs/shadow_diagnostic.json`** · **`outputs/ops_shadow_log.csv`** — 90일 관측용 (확장 필드)
- **`daily_report.md`** — Shadow 진단 4줄 + signal vs execution
- **`docs/MVP_v1.1a_SHADOW_MODE.md`** — shadow 범위·금지·허용·D+90 v1.1b 조건

### Notes
- 실거래 판단(`execution_scope`, SAA, target) **변경 없음** — `execution_authority: v1.0.2`

---

## [alpha-v0.2-shadow] — 2026-06-19

### Added
- **`src/alpha_v0_2/`** — Exclusion → Quality → Value → Momentum → Catalyst → Risk → Classifier
- **`data/alpha_v0_2.yaml`** — v0.2 weights·gates·risk budget
- **`docs/ALPHA_v0.2_CONCEPT.md`**
- Outputs: `alpha_v0_2_classification.csv`, `alpha_v0_2_shadow.json`, `alpha_v0_2_shadow_log.csv`, `alpha_v0_2_legacy_diff.json`
- `daily_report.md` — Alpha v0.2 Shadow 섹션 (보유 종목 분류)

### Added
- **`src/decision/duration_diagnostic.py`** — cash_short_bond → cash_short / kr_duration / global_duration shadow 분해
- **`data/duration_sleeve_tags.yaml`** — 슬리브 매핑 + v1.1b shadow SAA 참고치
- `shadow_diagnostic.json` · `ops_shadow_log.csv` · `daily_report` — Duration sleeve 라인

---

## [v1.0.2] — ops-lookthrough-v1 — 2026-06-25

### Added
- **Look-through 노출 레이더** — `data/look_through_tags.yaml`, `data/asset_group_labels.yaml`
- `outputs/exposure_lookthrough.json` — region / asset_class / currency / style 진단 집계
- `daily_report.md` — Look-through 노출 섹션 + 상단 운용 상태 4줄 요약
- `ai_export_bundle.json` — `exposure_lookthrough` 필드 포함
- AC-08: bundle에 `exposure_lookthrough` 누락 시 warn

### Changed
- 7자산군 target 계산·SAA/TAA·execution_scope·policy_cap 로직 **변경 없음** (진단 레이어만 추가)

### Fixed
- `test_portfolio_gap` — KODEX 200 목표비중 기대값 10.12% 동기화
- `test_target_draft_bridge` — 외부 draft 경로 의존 제거, `tests/fixtures/` + `tmp_path` 기반

---

## [v1.0.1] — ops-stabilized — 2026-06-25

### Added
- **Policy cap (운용 승인 안정화)** — technical vs operational 분리
  - `technical_status` — 게이트·dry-run 기준 (cap 적용 전)
  - `policy_cap` — FSR / `YELLOW_STABLE` 수동 레짐 상한
  - `operational_status` — cap 적용 후 최종 승인
- `outputs/final_execution_decision.json` — `policy_cap`, `technical_status`, `execution_permissions`
- `outputs/trigger_reviews.json` — KOSPI drawdown 트리거 검토
- `acceptance_report` schema 1.1 — `technical_overall`, `operational_overall`, `AC-POLICY-EXPIRY`
- Cross-validation CV-01~09, operational stabilization tests

### Fixed
- GREEN 오판 방지 — data gate RED 시 operational cap과 분리된 기술/운용 판정

---

## [v1.0.0] — MVP baseline

- 7자산군 SAA/TAA + 레짐 나침반 + 한국 알파 + 실행 게이트 MVP
