# AI 교차 검증 보고서 — 2026-07-09 (ai_cross_validation_20260709_1305.zip)

> 검증자: Claude (독립 검증) · 근거: 업로드된 번들(`ai_export_bundle.json`, `daily_report.md`, `system_health.json`, `*_validation.json`) + 저장소 소스코드 대조. 추측 없이 파일 근거만 사용.

## 종합 판정: **WARN**

전체 안전장치(Actual Buy Allowed=0, target_write 승인 체계, fail-closed 락)는 정상 작동 중이나, **알파 리포트 표에 "매수 트리거" 문구가 오해를 부를 수 있는 확인된 표시 버그 1건**을 발견해 WARN으로 판정합니다. 실제 매매 허용에는 영향 없음(안전불변식 훼손 아님).

---

### 데이터

- `health_report.overall = pass`, 개별 체크 전부 pass. Tier1 지표(kospi, vix, usdkrw, sp500, korea_10y, oil_brent, gold) 전부 값 존재, 0/결측 없음.
- 커버리지: `universe.csv` 2,768행 / `fundamentals.csv` 2,728행 / `prices.csv` 2,748행 — 상호 20~40행 차이, 투자판단에 치명적 수준 아님.
- **판정: PASS**

### 레짐·배분

- `computed_regime = CRISIS` (KOSPI 고점 대비 **-20.3%** 드로다운이 `kospi_crisis_drawdown` +1.00 만점 기여), `manual_regime = applied_regime = YELLOW_STABLE` (BOK FSR Jun-2026 근거 override, 만료 2026-09-24).
- **사실 확인**: score_breakdown 각 항목의 부호·기여도는 원자료(KOSPI/VIX/USDKRW 등)와 일치 — 계산 로직 자체는 정합.
- **판단 보류 사항 (사실과 구분)**: 드로다운이 최근 며칠 사이 -15%→-20.3%로 더 깊어지는 추세인데, 수동 override 근거(BOK FSR)는 6월 시점 자료입니다. `acceptance.items`의 **AC-05가 이미 "override 11영업일 경과 — 갱신 또는 만료 설정 권장"** 경고를 발행 중입니다 — 이는 제 추정이 아니라 시스템 자체가 낸 경고입니다. computed(CRISIS)와 applied(YELLOW_STABLE)의 간극이 벌어지고 있다는 사실과, 그 재검토를 시스템이 이미 요청하고 있다는 사실만 전달합니다. 유지할지 여부는 판단 보류.
- `asset_group_targets` 합계(kr_alpha final_target=25.01%)와 `gpt_context.kr_alpha_meta.kr_alpha_budget=25.01` **일치**. `kr_alpha_target_sum=24.38` vs budget → gap -0.63%p, 예산 초과 없음.
- **판정: WARN** (계산은 정합, 다만 override 재검토 타이밍이라는 시스템 자체 신호가 있음)

### Alpha

- `alpha_screening_meta.buy_permission_status = BLOCKED`. `alpha_top30_scored`/`alpha_grade_b_universe`/`alpha_replace_candidates` 전 종목 `buy_permission` 필드 **100% False** — 상태 불일치 없음 (validation_prompt 항목 "buy_permission_status와 모든 후보 buy_permission 일치 여부" → 일치).
- **확인된 버그 (표시 문구, 소스 특정)**: `reports/alpha_report_md.md`의 "매수 트리거" 컬럼에 **"alpha_auto_buy ALLOWED"** 문구가 7개 Buy-ready 종목 모두에 노출됩니다. 원본 JSON(`alpha_top30_scored[].risk_flag`)에는 정확히 반대로 **`"alpha_auto_buy_blocked"`**로 기록돼 있습니다.
  - 근본 원인: `src/alpha/alpha_signal_board.py:679-681`
    ```python
    if missing.get("execution_permission") == "blocked":
        triggers.append("alpha_auto_buy ALLOWED")
    ```
    이 리스트(`buy_trigger`)는 원래 "매수가 실행되려면 아직 충족해야 할 조건"을 나열하는 의도(예: "screener BUY_CANDIDATE grade" = 아직 미충족)이지만, 정작 이 줄만 조건명을 "ALLOWED"라는 완료형 단어로 적어놔서 — 표 위에서는 "Buy-ready" 상태 옆에 "ALLOWED"라는 단어가 그대로 노출됩니다. 의도(미충족 조건 나열)와 표현(완료형 단어)이 어긋난 명명 버그입니다.
  - 추가로 같은 표의 "부족 조건" 컬럼도 `missing_for_buy[:40]`, "매수 트리거" 컬럼은 `buy_trigger[:50]` 로 **고정 길이 절단**돼 있어(`alpha_signal_board.py:1133`), "eligible_action_buy_candidate:false"가 "eligible_a"로, "screener BUY_CANDIDATE grade"가 "...gr"로 단어 중간에 잘립니다 — 핵심 부정어(false, blocked)가 잘려나가는 경우 오해 소지가 더 커집니다.
  - **영향 범위**: 표시 텍스트만의 문제입니다. `buy_permission` 필드, `actual_buy_allowed`, 실행 게이트는 전혀 영향받지 않음 — 실거래 리스크 아님. 다만 리포트를 사람이 읽고 판단하는 용도이므로 수정 권장.
- `alpha_v2_policy_notes`에 **"Flow signal is not buy permission"**, **"KOSDAQ Shadow Watch is not buy permission"**, "Actual Buy Allowed=0 overrides all buy triggers/all KOSDAQ signals" 전부 포함 확인 — v2 쪽 disclaimer는 정상.
- v2 top30: KOSDAQ 3/30 (10%) — 과도한 쏠림 아님. `final_5_8`는 실제로 3종만 반환(목표 5~8종 미달) — 기존에 확인된 "숏리스트 최소 종수 미달" 문제의 연장선, 새로운 문제 아님.
- pension/foreign 수급 점수(`flow_score` 11~16점)는 `total_score_v2_shadow`(68~71점) 대비 비중이 작아 과도한 반영으로 보이지 않음.
- **판정: WARN** (표시 버그 1건, 그 외 로직/데이터 정합)

### 실행 리스크

- `daily_brief.system_status`: `authoritative_execution_scope = NO_TRADE`, `display_execution_scope = ETF_ONLY`, 설명 문구("ETF_ONLY is scope restriction, not ETF buy permission...") 그대로 노출 — 명확.
- `target_guard_conflict_detected = True`(오늘도 재발 — 기존에 확인된 ~4/17일 빈도 패턴과 일치) → fail-closed로 NO_TRADE 락. `target_write_audit`: 최근 승인 이벤트는 `approval_bridge` 경로, `approved_by_user: true`, `guard_result_after_write: PASS` — 정상 승인 흐름.
- **사실 확인(경미)**: `acceptance.overall/technical_overall/operational_overall = YELLOW`인 반면 `daily_brief.system_status.technical_status/market_status/full_status = RED`로 서로 다른 필드가 다른 심각도를 표시합니다. 스코프가 다른 필드(acceptance=게이트 판정, full_status=오늘 conflict 락 포함 종합)일 가능성이 높으나, 사람이 두 값을 나란히 보면 혼란 소지가 있어 사실만 기록합니다.
- `bundle_consistency_validation.json.diagnostics_verify.pass = false` (상위 `pass: true`와 별개 하위 체크) — 경고 2건: `policy_cap_counterfactual.json: missing field policy_cap`, `no_action_verify:status_alignment_pass_false`. 실행 게이트에 직접 영향 주는 항목은 아니나 진단 파일 완결성 이슈로 별도 확인 권장.
- **판정: WARN** (안전장치 자체는 정상, 진단 파일 완결성 경고 2건 미해결)

### 권고 (사람 승인 전)

**Cursor 조치 대상 (코드 수정)**

1. **[최우선, 근거 명확]** `src/alpha/alpha_signal_board.py:679-681`의 `"alpha_auto_buy ALLOWED"` 문구를 `"alpha_auto_buy 승인 필요(현재 BLOCKED)"` 등 명확한 표현으로 수정. `buy_trigger`/`missing_for_buy` 절단 길이(`alpha_signal_board.py:1133`, 각각 `[:50]`/`[:40]`)도 핵심 단어(blocked/false)가 잘리지 않도록 늘리거나 단어 경계에서 자르도록 수정. 이 항목은 원인 파일·라인·현재 코드·기대 동작이 이미 확정돼 있어 바로 수정 가능.
2. **[조사 후 원인+제안만 보고, 즉시 수정 금지]** `bundle_consistency_validation.json`의 `diagnostics_verify` 하위 경고 2건 — `policy_cap_counterfactual.json: missing field policy_cap`, `no_action_verify:status_alignment_pass_false`. 어느 함수가 이 필드를 채워야 하는데 안 채웠는지 원인만 특정해서 보고해달라고 요청할 것 — 원인에 따라 안전불변식 관련 파일을 건드릴 수도 있으므로 원인 확인 전 임의 수정 금지.
3. **[조사 후 보고]** `acceptance.overall`(YELLOW)과 `system_status.full_status`(RED)가 왜 다른 심각도를 보이는지 — 스코프가 원래 다른 필드라면(예: full_status가 오늘의 target_guard_conflict 락을 추가 반영) 그 사실만 확인하고, 리포트에 한 줄 설명을 추가하는 선에서 제안.

**운영자(동준) 판단 대상 — Cursor에게 코드 수정을 요청할 사안 아님**

4. YELLOW_STABLE 수동 override — `policy_cap.py`는 절대 수정 금지 파일입니다. AC-05가 이미 "override 11영업일 경과, 갱신/만료 검토 권장" 경고를 냈으니, 유지·갱신·조기종료 여부는 동준님이 직접 판단할 사안입니다(실행에 즉시 영향 없음 — 오늘 authoritative scope는 어차피 NO_TRADE). Cursor에게 전달 시 이 항목은 "코드 조치 아님, 정보 공유용"이라고 명시할 것.

이번 발견 중 실행 게이트·안전불변식(actual_buy_allowed, target_write, approval_bridge)을 훼손하는 항목은 없습니다.
