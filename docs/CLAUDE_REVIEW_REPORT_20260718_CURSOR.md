# 검수 결과 — SAA 알파 2026-07-18

> **역할:** 독립 검수 보고 (코드 수정 없음)  
> **작성:** Cursor 세션이 브리프 기준으로 교차 검수 (완전 외부 Claude와 동일 템플릿)  
> **대상 HEAD:** `da46383` (브리프 포함) / 안정판 `stable-20260718-final-selection`  
> **사전 테스트:** focused 41 passed (`select_eligible`·sizing·weekly·triggers·action_panels·cecs parser)  
> **작성일:** 2026-07-18

---

## 요약 (3줄 이내)

- Critical: **0**
- Major: **2**
- Minor/메모: **3**
- 불변 규칙 위반(즉시 돈·target 자동변경): **없음**

설계–구현 정합은 대체로 탄탄하다. 다만 목표가 membership 게이트가 **fail-open / 순환 allowlist** 가능성이 있고, `attempt_execute` 목표가 차단은 **인자를 넘길 때만** 동작해 UI와 이중 경로다.

---

## Critical

*(해당 없음)*

불변 규칙 1–6을 깨는 live 경로(하케다카로 순위 변경, `target_portfolio.csv` 자동쓰기, FASTJUSIK, 상대순위 확정 UI, CECS B/E 폴백)는 확인되지 않았다.

---

## Major

### M1. 목표가 승인 membership 게이트가 fail-open + 순환 allowlist
- **파일:** `alpha_system/ui/services/weekly_domain_gates.py` (`_apply_targets`, ~299–308)  
  `alpha_system/ui/services/weekly_qual_report.py` (`persist_weekly_suggestions`, ~416–427)
- **문제**
  1. `if allowed and ticker not in allowed:` — `deep_tickers`가 비어 있으면 멤버십 검사가 **실행되지 않음**(fail-open).
  2. import persist 시 `deep_tickers`를 `deep_dives ∪ targets`로 재구성 — 업로드 MD의 목표가 섹션에 넣은 티커가 allowlist에 **스스로 들어가** 게이트를 우회할 수 있음.
- **왜 규칙과 관련:** 주간 B/E = proposal_book만 / final 밖 목표가 승인 거부라는 P0 주장과 어긋날 수 있음. `target_portfolio.csv`는 해시로 보호되나, `kr_alpha_exit_targets.yaml`에 proposal 밖 종목이 승인될 여지.
- **재현 요지:** `deep_tickers: []`인 suggestions JSON, 또는 targets에만 있는 티커로 persist 후 targets 승인.
- **확신도:** high (코드 경로 직접 확인)
- **트리아지 메모:** ①·③ 필터상 불변/하드닝 직결 → **채택 후보**. 수정은 별도 승인 후 Cursor 구현.

### M2. `attempt_execute` 목표가 게이트는 호출자가 `entry_tickers`를 넘길 때만 동작
- **파일:** `alpha_system/entry/evaluate.py` (~877)  
  `alpha_system/ui/services/action_panels.py` `_panel_execute` (~281–316)
- **문제:** `if blocked is None and entry_tickers and cfg.exit.entry_require_target_valuation:`  
  `entry_tickers`가 없거나 빈 시퀀스면 목표가 하드블록이 **스킵**된다.  
  현재 UI 체결은 `attempt_execute`를 쓰지 않고 `TRANCHE_EXEC_FILL` + 패널 내 `check_entry_target_valuation`으로 막는다(이중 경로).  
  프로덕션에서 `attempt_execute(...)`를 인자 없이 호출하는 live 코드는 테스트 외 **없음**(grep).
- **왜 Major이지 Critical이 아닌가:** 지금 돈이 기록되는 UI 경로는 별도 차단됨. 다만 “엔진 게이트 = SoT”로 보면 방어선이 갈라져 있음.
- **확신도:** high
- **트리아지 메모:** ② 관련 — 패널 로직 결함이라기보다 **엔진·UI 이원화**. Critical 아님. 일원화는 Major 개선.

---

## Minor · 개선 제안

### m1. 보험(`insurance`)은 `financial` 캡에 미포함
- `sector_map.CONCENTRATION_ALIASES`는 `financial_bank→financial`만. taxonomy상 보험은 `insurance` 별도.
- 은행+지주 최대 2 + 보험 최대 2 = 금융권 테마 4종 가능.  
  과거 논의(위기 시 상관↑)와 **의도적 분리**일 수 있음 — 정책 재확인만.
- **확신도:** medium (정책 판단, 버그 단정 아님)

### m2. `max_names_per_sector`의 `getattr(..., 2) or 2`
- `allocate_tranche`에 스키마 기본과 중복된 silent fallback. 알려진 “리터럴 폴백” 경계선과 동류.
- **확신도:** high · Critical 아님(P2 절제)

### m3. CECS 30 매직넘버 · 전체 pytest hang
- 브리프 P2 그대로 — 의견만. 이번 수정 지시 없음.

---

## 확인 완료 (문제 없음)

- [x] **섹터 캡 + financial alias** — `select_eligible`은 `eligibility is True`만, shortfall 시 완화 없음. iterative capping은 **이미 선정된 eligible** 안에서만 재분배하고 신규 종목을 끌어오지 않음 (`allocate.py`). 테스트 `test_select_eligible_sector_cap.py`가 핵심 엣지 커버. ①: 기존 커버 재확인 → 이상 없음; **새 엣지 미발견**.
- [x] **목표가 편입 차단 (UI)** — `_sizing_excerpt`가 suggested에서 제외, `_panel_execute`가 종목별 차단. config `entry_require_target_valuation: true`.
- [x] **주간 B/E proposal-only (생성 경로)** — `events.py`가 `portfolio_rows[:n_deep]`만, 비면 버튼 disabled. CECS summary fallback 문구/코드 없음.
- [x] **상대순위 확정 경로 제거** — `alpha_system/**/*.py`에 `relative_rank_slider` / `cutoff_relative` 없음. 체크리스트는 `cutoff_goto_portfolio`. 확정 SoT = `portfolio.py` `absolute_cutoff_then_count`.
- [x] **대체 API 라이브 제거 + 파서 유지** — `write_cecs_ai_research_report` / `save_cecs_score` live 없음. parse·approve·reopen 유지.
- [x] **oneshot scripts archive** — `archive/20260718_oneshot_scripts/` 존재; `scripts/remove_030190_clean_run.py` 경로 없음(Test-Path False).
- [x] **② 옛 테스트 실패** — `test_checklist_blocks_incomplete`는 config에 cutoff가 있으면 score_cutoff 미차단이 정상. **패널 로직 Critical 아님** → “테스트가 진화 못 따름 / 이미 cutoff=None으로 개정됨” 갈래.

---

## 보류 항목에 대한 의견 (수정 지시 금지)

- **E (이중 앱):** `app.py` vs `alpha_dashboard.py` 공존은 의도적 보류로 유지. 검수 범위 밖.
- **30종 매직넘버:** config화는 있으면 좋음, 당장 Critical 아님.
- **전체 pytest hang:** PyKRX 네트워크 — 환경. focused 세트로 회귀 충분한 상태.

---

## ①②③ 교차 메모 (합의 트리아지)

| 관심 | 결과 |
|------|------|
| ① allocate shortfall | 원칙 유지. 새 엣지 Critical/Major **없음**. |
| ② action_panels vs 옛 테스트 | 패널 Critical **아님**. M2는 엔진 이원화(Major). |
| ③ Critical 건수 | **0** — 불변 직결 위반 미검출. Major 2는 “방어선 구멍/약화” 성격. |

---

## 확신도

- **전체:** medium–high (저장소 직접 읽음 + focused 테스트; 외부 Claude 완전 독립은 아님 — 확증 편향 잔존 가능)
- **못 본 것:** Streamlit 실클릭 E2E, 증권사 체결 실무 경로, 레거시 `app.py` 전면

---

## 다음 액션 제안 (보고만 — 실행은 별도 승인)

채택 시 Cursor 수정 후보:
1. **M1:** `deep_tickers`를 **생성 시점 proposal만** 고정 저장; import 시 targets로 allowlist 확장 금지; `allowed` 비면 승인 거부(fail-closed).
2. **M2:** UI 체결도 `attempt_execute(..., entry_tickers=..., has_target_by_ticker=...)`로 모으거나, `entry_tickers is None`일 때 목표가 게이트를 기본 적용할지 정책 결정.

외부 Claude 보고서가 오면 이 문서와 diff 대조해 중복·신규만 남기면 된다.
