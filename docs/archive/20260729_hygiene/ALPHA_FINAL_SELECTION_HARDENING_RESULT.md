# 최종선정 갭보완 — 검증 정리 (Claude 검증용)

> **목적:** 2026-07-17~18에 진행한 "정량→최종선정→주간정성→편입차단" 파이프라인 하드닝을
> 다른 AI(클로드)나 사람이 **독립적으로 재검증**할 수 있게 한 곳에 모은다.
> **코드 루트:** `C:\Cursor\investment-saa-alpha` only
> **작성일:** 2026-07-18

---

## 0. 한 줄 요약

절대 `score_cutoff` 통과 → **섹터당 ≤2**(`sector_group`, 은행·금융지주 동일 테마) → **5~8종**(기본 6) 순으로
객관 최종선정을 만들고, **목표가 승인이 없는 종목은 편입(체결) 차단**(다음 주 통합보고서 E까지 대기).
주간 정성 요청서의 심층/목표가(B/E)는 **현재 proposal_book만** 사용하고 CECS 상위 N 폴백을 제거.

---

## 1. 불변 규칙 준수 확인 (변경이 위반하지 않음)

- `proposal_mode: pure_qvm` — 하케다카·수급으로 순위/target 자동변경 없음 ✅ (선정은 `total_score`/`weight_input`만 사용)
- `target_portfolio.csv` 자동 변경 금지 — 사람 승인 UI만 ✅ (이번 변경은 proposal_book·차단 게이트만 손댐)
- ETF Executable / kr_alpha Review-only ✅ (편입차단은 kr_alpha 체결 기록을 막는 쪽)
- 하드코딩 종목/소스 고정 없음 ✅ (섹터는 `data/krx_sector_mapping*.csv`에서 로드, 목표가는 `kr_alpha_exit_targets.yaml` 승인분에서 로드)

---

## 2. 변경된 로직 (검증 포인트)

### 2.1 섹터 집중 캡 (핵심)
- 파일: `alpha_system/sizing/allocate.py` → `select_eligible(...)`
  - 입력: `eligibility is True` 인 종목만. `eligibility is None`(cutoff TODO)은 제외 + 경고.
  - 정렬: `weight_input` 내림차순.
  - 캡: 정규화된 `sector_group` 버킷당 `max_names_per_sector`(기본 2) 초과 시 skip.
  - 상한: `target_names`에서 stop. 부족(shortfall)이면 **컷오프·섹터캡을 완화하지 않고 그대로 부족** 허용 + 경고.
  - 미지 섹터("" / unknown)는 `unknown:{ticker}` 로 **종목별 고유 버킷** → 우연한 집중 방지.
- 파일: `alpha_system/sizing/sector_map.py` (신규)
  - `load_sector_groups(data_dir)` — `krx_sector_mapping.csv` + `_manual.csv` 병합(우선순위 manual>official>infer).
  - `concentration_bucket(...)` + `CONCENTRATION_ALIASES = {"financial_bank": "financial"}`
    → **은행 ≡ 금융지주** 를 하나의 테마 캡으로 합침 (과집중 방지).
- 설정: `alpha_system/config/alpha_system.yaml` → `sizing.max_names_per_sector: 2`
- 스키마: `alpha_system/schema.py` → `SizingConfig.max_names_per_sector: Field(2, ge=1, le=8)`,
  `target_names: Field(..., ge=5, le=8)`

### 2.2 섹터 소스 배선 (동일 SoT 사용)
같은 sector 값이 3경로에서 동일하게 흐르도록 배선:
- `alpha_system/scoring/engine.py` → `NameScore.sector` 필드 추가
- `alpha_system/ui/services/context.py` → `ScoreboardRow.sector`, `_build_scoreboard`가 `load_sector_groups`로 채움 → proposal preview/allocate에 전달
- `alpha_system/report/screen_dry.py` → dry CLI도 동일 `sector_map` 사용 (UI proposal == dry CLI 결과)

### 2.3 목표가 편입 하드블록
- `alpha_system/entry/evaluate.py` → `attempt_execute(...)`에 `entry_tickers`/`has_target_by_ticker` 인자.
  `cfg.exit.entry_require_target_valuation`이 켜져 있고 목표가 없는 후보가 있으면 `WARN_BLOCKED`(blocked=True).
- `alpha_system/ui/services/action_panels.py`
  - `_exit_target_tickers(ctx)` — `kr_alpha_exit_targets.yaml`의 승인 티커 집합.
  - `_panel_execute` — 목표가 없는 종목은 "대기 후보(편입 차단)" 경고 + 개별 체결 입력 차단.
  - `_sizing_excerpt` — 목표가 없는 종목은 배분 참고만, 체결 제안(suggested)에서 제외.

### 2.4 주간 정성 B/E 게이트
- `alpha_system/ui/pages/events.py` — 심층/목표가(B/E)는 `ctx.portfolio_rows[:target_names]`(현재 proposal_book)만.
  proposal_book이 비면 요청서 생성 자체를 막음(CECS 상위 N 폴백 제거).
- `alpha_system/ui/services/weekly_qual_report.py` — `write_weekly_qual_report`가 `deep_subjects` 없으면 `ValueError`.
  `persist_weekly_suggestions`가 `deep_tickers`(심층+목표가 티커) 저장.
- `alpha_system/ui/services/weekly_domain_gates.py` — `_apply_targets`가 `deep_tickers` 밖 티커의 목표가 승인을 거부.

---

## 3. 재검증 방법 (명령)

```powershell
# 핵심 회귀 (약 4초)
python -m pytest -q -p no:cacheprovider `
  tests/test_select_eligible_sector_cap.py `
  tests/test_alpha_system_sizing.py `
  tests/test_weekly_qual_report.py `
  tests/test_alpha_system_triggers_final.py `
  tests/test_action_panels.py

# 임포트 스모크
python -c "import alpha_system.ui.services.context, alpha_system.report.screen_dry, alpha_system.entry.evaluate, alpha_system.sizing.allocate, alpha_system.sizing.sector_map; print('OK')"
```

**기대:** 위 5개 파일 전부 pass (마지막 검증 시 37 passed). 임포트 OK.

> 참고: 저장소 전체 `pytest`는 `alpha_portfolio/tests/test_collect.py` 등 PyKRX **네트워크 의존 테스트에서 멈춤**.
> 이는 이번 변경과 무관한 환경 이슈 → 위 focused 세트로 검증.

---

## 4. 검증 기준 (acceptance)

| # | 기준 | 확인 테스트 |
|---|------|-------------|
| A | 같은 섹터 3번째 종목은 캡으로 skip, shortfall 경고 | `test_sector_cap_keeps_top_two_per_group` |
| B | 부족해도 컷오프/캡 완화로 강제 채우지 않음 | `test_sector_cap_shortfall_does_not_force_fill` |
| C | 미지 섹터는 종목별 버킷(집중 안 됨) | `test_unknown_sector_uses_per_ticker_bucket` |
| D | eligibility=False는 섹터 압력에도 절대 선정 안 됨 | `test_ineligible_never_selected_under_sector_pressure` |
| E | 은행(financial_bank)≡금융지주(financial) 한 캡 | `test_financial_bank_rolls_into_financial_cap` |
| F | 목표가 없는 대기후보는 체결 차단(WARN_BLOCKED) | `test_attempt_execute_blocked_without_exit_yaml` |
| G | 목표가 전부 있으면 실행 허용 | `test_attempt_execute_allows_when_all_targets_present` |
| H | proposal 없으면 B/E 요청서 생성 실패 | `test_weekly_be_requires_deep_subjects` |
| I | final 밖 티커의 목표가 승인 거부 | `test_apply_targets_rejects_ticker_not_in_final_snapshot` |

---

## 5. 알려진 경계선 (이번에 손대지 않음)

- CECS "30종" 요건이 `cecs_workbench.py` 3곳에 매직넘버 (config화 미비).
- `scripts/validate_signal_board_run.py`에 기대 티커 목록 고정 (검증 하네스, 실무 영향 낮음).
- 저장소 전체 pytest 네트워크 hang (PyKRX 수집 테스트).
- 다음 개발: 죽거나 버려진 기능 정리 (별도 SPEC 예정).
