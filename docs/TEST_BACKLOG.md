# Legacy Failed Tests Backlog (P4b)

> **분리 원칙:** P0~P3d 성능·cache 최적화와 **별도 이슈**. 테스트를 억지로 통과시키지 않고, 현재 운용 정책과 맞지 않는 fixture/expected를 분류합니다.  
> **기준일:** 2026-07-08 (P4b)  
> **전체 스위트:** ~792 collected (2 collection error) · full run ~36분 · **목표 정리: 20건 내외**

---

## 요약

| 카테고리 | 건수 (확인됨) | 처리 방향 |
|----------|-------------|-----------|
| `import_stale` (collection error) | 2 | import/API rename 정리 또는 테스트 격리 |
| `profile_fixture_mismatch` | 5 | `defensive_balanced` ↔ `core_absolute_return` fixture 통일 |
| `compass_expected_output_stale` | 1 | SAA/TAA cash floor expected 갱신 |
| `alpha_policy_fixture_stale` | 2+ | alpha pipeline empty candidates / priority expected |
| `pipeline_cache_output_changed` | 5+ | run_mode·authoritative scope·alert 라벨 반영 |
| `external_data_dependency` | 5+ | mock/fail-soft 분리 또는 `@pytest.mark.network` |

**확인 PASS (이전 backlog, 현재 통과):** `tests/test_run_mode_contract.py`, `tests/test_alpha_v2_cache_decision.py` (21 passed, 2026-07-08)

## 상세 backlog (P4b+)

| test_name | category | current_failure | likely_cause | whether_blocks_operation | fix_policy | owner_next_action |
|-----------|----------|-----------------|--------------|--------------------------|------------|-------------------|
| `tests/test_compass.py` (4건) | profile_fixture_mismatch | `core_absolute_return` expected | SAA default 프로필 변경 | **false** (4건 unit 수정 완료) | fixture expected 갱신 | ✅ 완료 |
| `tests/test_ui_menus.py::test_saa_backtest_static_weights` | profile_fixture_mismatch | profile name | 동일 | **false** | expected 갱신 | ✅ 완료 |
| `tests/test_portfolio_selector.py` (2건) | alpha_policy_fixture_stale / profile | empty candidates, weight sum | universe/hakedaka overlap | **false** | synthetic fixture | integration tier |
| `tests/test_p0_alignment.py::test_acceptance_scope_matches_decision_log` | pipeline_cache_output_changed | NO_TRADE vs ETF_ONLY | authoritative vs display scope | **false** | dual-scope test doc | backlog |
| `tests/test_report_consistency.py` | pipeline_cache_output_changed | Trim label text | alert wording change | **false** | expected 갱신 | backlog |
| `tests/test_v2_features.py::test_full_pipeline` | pipeline_cache_output_changed | full pipeline drift | cache step outputs | **false** | integration refresh | manual |
| `tests/test_alpha_screener.py` (다수) | alpha_policy_fixture_stale | candidates/API | alpha v1 schema | **false** | fixture/mock | integration |
| `tests/test_benchmark_data_quality.py` | external_data_dependency | return_mtd None | live price missing | **false** | mock CSV | external_data tier |
| `tests/test_tier_a_price_gate.py` | external_data_dependency | gate pass vs fail | sample data changed | **false** | isolated fixture | backlog |
| `tests/test_hakedaka_evidence_enrichment.py` | import_stale | `_extract_amounts` | API rename | **false** | public API 사용 | ✅ 완료 |
| `tests/test_run_mode.py` | import_stale | `store_input_hash` import | moved to cache_decision | **false** | import fix | ✅ 완료 |
| `tests/test_core_etf_permission_diagnostics.py::test_policy_cap_etf_scenario_clarity_fields` | pipeline_cache_output_changed | `alpha_path_blocker` expected `shortlist_eligible=0` got `alpha_auto_buy_permission=BLOCKED` | live `alpha_shortlist_summary.json` shortlist_eligible>0 after market day drift; assertion hard-codes zero eligible | **false** (P5-A 무관, policy_cap_counterfactual mtime 불변) | mock shortlist fixture 또는 expected를 조건부 | backlog (2026-07-08 신규, 34번째) |

**fast suite:** operation_blocking_failures = **0** · backlog 목록 **34건** (P5-A 검증 중 1건 신규 기록)

**데이터 한계 (운용 비차단):** `data/prices_history.csv` D1 초기 버그로 9,205→7,961행 축소(2026-07-09). alpha_gate/hakedaka 커버리지 지표 사고 전후 동일 확인 → **복구 보류**. 상세: `docs/P5D_HISTORY_BACKFILL_SINCE_INCEPTION_SPEC.md` §9.1.


---

| 테스트 | 원인 | 조치 |
|--------|------|------|
| `tests/test_hakedaka_evidence_enrichment.py` | `_extract_amounts` import 없음 (`hakedaka_treasury_events`) | private API 제거 대응: public helper 노출 또는 테스트 삭제/격리 |
| `tests/test_run_mode.py` | `store_input_hash` import 없음 (`alpha_v2.input_hash`) | cache API rename 반영 또는 legacy 테스트 archive |

---

## 2. profile_fixture_mismatch

**공통 원인:** `data/saa_profiles.yaml` / 나침반 기본 프로필이 `core_absolute_return`으로 운영 중인데, 테스트 fixture는 `defensive_balanced` 기대.

| 테스트 | 실패 요약 |
|--------|-----------|
| `tests/test_compass.py::test_profile_alias_balanced_to_defensive_balanced` | `core_absolute_return` != `defensive_balanced` |
| `tests/test_compass.py::test_build_allocation_sums_to_100` | 동일 프로필 불일치 |
| `tests/test_compass.py::test_pipeline_outputs` | 동일 |
| `tests/test_ui_menus.py::test_saa_backtest_static_weights` | 동일 |
| `tests/test_portfolio_selector.py::test_saa_taa_ticker_tables` | ticker weight sum 87% vs 100% (프로필·TAA 변경) |

**조치:** (A) 테스트 fixture를 `core_absolute_return` 기준으로 갱신, 또는 (B) 테스트 전용 `saa_profiles` stub 사용. **운영 YAML 변경 금지.**

---

## 3. compass_expected_output_stale

| 테스트 | 실패 요약 |
|--------|-----------|
| `tests/test_compass.py::test_crisis_cash_above_policy_minimum` | crisis cash `final_target` 38.64 < expected 50 |

**조치:** `core_absolute_return` 프로필·TAA 규칙에 맞는 expected 재산정.

---

## 4. alpha_policy_fixture_stale

| 테스트 | 실패 요약 |
|--------|-----------|
| `tests/test_portfolio_selector.py::test_alpha_pipeline_writes_proposal` | `candidates == []` (hakedaka overlap 0) |
| `tests/test_action_planner.py::test_kr_alpha_replace_theoretical_low_priority` | priority `High` vs expected `Low` |
| `tests/test_alpha_screener.py` (다수) | 과거 `TypeError: BaseModel...` — alpha v1 API/schema drift (11 tests, 재확인 필요) |

**조치:** synthetic universe/DART fixture로 후보 1건 이상 보장; alpha policy 변경에 맞게 expected 갱신.

---

## 5. pipeline_cache_output_changed

run_mode·cache·authoritative status 도입 후 산출물/라벨 변화.

| 테스트 | 실패 요약 |
|--------|-----------|
| `tests/test_p0_alignment.py::test_acceptance_scope_matches_decision_log` | `NO_TRADE` vs `ETF_ONLY` |
| `tests/test_report_consistency.py::test_trigger_alerts_kr_risk_trim_not_labeled_theoretical` | Trim 라벨 문구 변경 |
| `tests/test_portfolio_gap.py::test_compute_gaps_sample` | `StopIteration` (sample gap fixture) |
| `tests/test_v2_features.py::test_full_pipeline` | full pipeline integration (slow, 산출물 drift) |
| `tests/test_alpha_shadow_config.py` (lastfailed) | v0.2 shadow on/off pipeline (테스트명·API 변경) |

**조치:** authoritative `NO_TRADE` vs display `ETF_ONLY` 이중 표기 정책을 테스트 docstring에 명시 후 expected 갱신.

---

## 6. external_data_dependency

| 테스트 | 실패 요약 |
|--------|-----------|
| `tests/test_benchmark_data_quality.py::test_combined_prices_mtd_not_zero_for_sp500` | `return_mtd is None` |
| `tests/test_benchmark_data_quality.py::test_core_benchmark_uses_combined_prices` | `core_saa_return_mtd is None` |
| `tests/test_asset_accumulation_timing.py::test_ready_does_not_imply_executable_without_green` | block reason `prohibited_stale_input` vs `blocked` |
| `tests/test_tier_a_price_gate.py::test_tier_a_gate_fail_trade_actions_missing` | gate `pass` vs expected `fail` |
| `tests/test_top10_sector_candidate.py::test_extract_unknown_excludes_manual_mapped` | ticker `001450` 미포함 |
| `tests/test_risk_limits.py::test_db_insurance_overweight_in_sample` | (lastfailed — sample data drift) |

**조치:** `@pytest.mark.network` / price CSV fixture mock; fail-soft reason enum 문서화 후 expected 정렬.

---

## 우선순위 (P4b → P4b+)

1. **import_stale (2)** — collection unblock (전체 CI 가시성)
2. **profile_fixture_mismatch (5)** — 가장 많은 연쇄 실패
3. **pipeline_cache_output_changed (5)** — 운영 정책과 alignment 테스트 갱신
4. **external_data_dependency (5)** — mock 분리
5. **alpha_policy_fixture_stale** — synthetic fixture

---

## 실행 메모

```powershell
# collection error 제외 fast subset (~15분, network/slow 제외)
python -m pytest --ignore=tests/test_hakedaka_evidence_enrichment.py --ignore=tests/test_run_mode.py -m "not network and not slow and not pykrx" -q

# 카테고리별
python -m pytest tests/test_compass.py -q
python -m pytest tests/test_portfolio_selector.py tests/test_p0_alignment.py -q
```

---

## 관련

- `tests/backlog/README.md` — backlog 디렉터리 안내
- `docs/RUN_MODE_POLICY.md` — run_mode 운영 고정
- `outputs/standard_cache_hit_baseline.json` — P4a baseline (성능 회귀 기준)
