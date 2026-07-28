# Claude 독립 검수 브리프 — SAA 알파 (2026-07-18)

> **이 파일을 Claude에 그대로 붙이거나 업로드한 뒤**, 아래 「검수 미션」을 수행하게 하세요.  
> **코드 루트:** `C:\Cursor\investment-saa-alpha` only  
> **안정 태그:** `stable-20260718-final-selection` (= 커밋 `614a87c` 계열)  
> **정리 후 HEAD:** `b0e42ef` (cleanup B+D)  
> **Cursor 측 사전 검증:** focused pytest 통과 · 전체 pytest는 PyKRX 네트워크 hang으로 제외

---

## 검수 미션 (Claude에게)

당신은 **구현자가 아닌 독립 검수자**다. 코드를 고쳐 쓰지 말고, 아래만 보고한다.

1. **불변 규칙 위반**이 있는지  
2. **설계와 다른 살아 있는 경로**(죽은 정책이 UI/API에 남아 있는지)  
3. **하드코딩·silent default·소스 고정** 여부  
4. **테스트가 주장과 일치하는지**(테스트만 통과하고 로직이 빈약한 경우 지적)  
5. **정리(A~D) 후 잔재·깨진 import·죽은 참조**

출력 형식은 맨 아래 「보고 템플릿」을 따른다. 추측이면 `확신도: low`로 표시하고, 파일 경로를 인용한다.

---

## 불변 규칙 (어기면 즉시 Critical)

| # | 규칙 |
|---|------|
| 1 | `proposal_mode: pure_qvm` — 하케다카·수급으로 제안 순위·`target_portfolio` 자동 변경 금지 |
| 2 | `target_portfolio.csv`는 **사람 승인 UI만** 변경. 스크립트·스크린·주간승인으로 자동 쓰기 금지 |
| 3 | Executable = ETF·현금·채권(scope 허용 시). **kr_alpha·하케다카·수급 = Review-only** |
| 4 | FASTJUSIK 스크래핑 금지 — PyKRX/DART만 |
| 5 | AC-HK: 유동성 실패 편입 금지, hard_slot OFF, shadow만 |
| 6 | 종목·데이터 소스를 코드에 **확정적 하드코딩**하지 말 것 (매핑 CSV·YAML·config에서 로드) |

---

## 이번에 검수할 범위 (우선순위)

### P0 — 최종선정 하드닝 (기능 정확성)

상세: `docs/ALPHA_FINAL_SELECTION_HARDENING_RESULT.md`

| 주제 | 기대 동작 | 읽을 파일 |
|------|-----------|-----------|
| 절대 cutoff → 섹터당≤2 → 5~8 | shortfall 시 컷/캡 **완화 금지** | `alpha_system/sizing/allocate.py` `select_eligible` |
| 은행≡금융지주 한 캡 | `financial_bank` → `financial` | `alpha_system/sizing/sector_map.py`, `data/krx_sector_taxonomy.yaml` |
| UI proposal == dry CLI | 동일 `sector_map` SoT | `ui/services/context.py`, `report/screen_dry.py` |
| 목표가 없으면 편입 차단 | 대기후보·체결 제외 | `entry/evaluate.py`, `ui/services/action_panels.py` |
| 주간 B/E = proposal만 | CECS 상위 N 폴백 **없어야 함** | `ui/pages/events.py`, `weekly_qual_report.py`, `weekly_domain_gates.py` |
| 컷오프 확정 SoT | **포트폴리오만** 절대컷+5~8. 체크리스트에 상대순위 확정 **없어야 함** | `ui/pages/portfolio.py`, `ui/services/action_panels.py` `_panel_checklist_cutoff` |

**Acceptance (코드로 확인):**

- [ ] `alpha_system/**/*.py`에 `relative_rank_slider` / `method="relative_rank` 확정 경로 없음  
- [ ] `select_eligible`이 `eligibility is not True`를 절대 강제 편입하지 않음  
- [ ] `max_names_per_sector` 기본 2, `target_names` 스키마 5~8  
- [ ] B/E 생성 시 proposal 비면 실패 / targets 승인 시 `deep_tickers` 밖 거부  
- [ ] `attempt_execute` 또는 UI 체결이 목표가 없는 티커를 막음  

테스트 근거: `tests/test_select_eligible_sector_cap.py`, `test_weekly_qual_report.py`, `test_alpha_system_triggers_final.py`, `test_alpha_system_sizing.py`

### P1 — cleanup A+C+B+D (잔재·회귀)

상세: `docs/CODEBASE_CLEANUP_AC_20260718_RESULT.md`, `docs/CODEBASE_CLEANUP_BD_20260718_RESULT.md`

| 주제 | 기대 | 확인 |
|------|------|------|
| A 죽은 UI | `cecs_scoring`/`settings` 페이지 라이브 import 0 | `archive/20260718_dead_ui/` |
| C 상대순위 제거 | 체크리스트는 포트폴리오로 안내만 | `action_panels.py`, `docs/UI_COPY.md` `cutoff_absolute_help` |
| B 대체 API | live에 `write_cecs_ai_research_report`/`save_cecs_score`/`ai_verification_report` import 경로 없음. **파서·approve·reopen은 유지** | `cecs_ai_research.py`, `cecs_workbench.py` |
| D 일회성 스크립트 | `scripts/`에 target-write 원샷 8개 없음 | `archive/20260718_oneshot_scripts/` |

**유지해야 하는 것 (삭제되면 버그):**

- `parse_cecs_ai_research_markdown`, `USAGE_WARNING`, `CecsResearchSubject`  
- `import_ai_suggestions` / `approve_ai_suggestions` / `reopen_final_for_rescoring`  
- `confirm_score_cutoff` + 포트폴리오 `method="absolute_cutoff_then_count"`  

### P2 — 검수만, 수정 범위 밖 (보고만)

- **E:** `app.py`(레거시 multi_asset UI) vs `alpha_dashboard.py`(알파 결재함) 공존 — 지금은 **의도적 보류**. “둘 중 하나를 지우라”고 결론내지 말 것. 위험·중복 여부만 메모.  
- 전체 pytest hang (PyKRX) — 환경 이슈로 기록만.  
- CECS “30종” 매직넘버 (`cecs_workbench`) — 알려진 경계선, 이번 Critical 아님.  

---

## Claude에 같이 줄 자료 (권장 첨부 순서)

1. **이 브리프** (`docs/CLAUDE_REVIEW_BRIEF_20260718.md`) — 필수  
2. `docs/ALPHA_FINAL_SELECTION_HARDENING_RESULT.md` — 필수  
3. `docs/CODEBASE_CLEANUP_AC_20260718_RESULT.md`  
4. `docs/CODEBASE_CLEANUP_BD_20260718_RESULT.md`  
5. (가능하면) 핵심 파일 원문 또는 저장소 접근:
   - `alpha_system/sizing/allocate.py`
   - `alpha_system/sizing/sector_map.py`
   - `alpha_system/ui/pages/portfolio.py`
   - `alpha_system/ui/services/action_panels.py` (`_panel_checklist_cutoff`, `_panel_execute`, `_sizing_excerpt`)
   - `alpha_system/entry/evaluate.py` (`attempt_execute`)
   - `alpha_system/ui/pages/events.py` (주간 B/E)
   - `alpha_system/ui/services/weekly_domain_gates.py` (`_apply_targets`)
   - `alpha_system/ui/services/cecs_ai_research.py` (파서만 남아 있는지)
   - `tests/test_select_eligible_sector_cap.py`

저장소 전체 zip은 비추천(노이즈). 위 파일 + RESULT면 충분.

---

## Cursor가 이미 한 일 (중복 검수 줄이기)

| 커밋 | 내용 |
|------|------|
| `614a87c` + tag `stable-20260718-final-selection` | 최종선정 하드닝 안정판 |
| `52bf2ec` | cleanup A+C |
| `b0e42ef` | cleanup B+D |

Cursor focused 테스트: sector_cap / sizing / weekly / triggers / action_panels / cecs parser·workbench 등 **pass**.  
Claude는 **재실행보다 논리·잔재·규칙 위반**에 집중.

---

## 보고 템플릿 (Claude 출력)

```markdown
# 검수 결과 — SAA 알파 2026-07-18

## 요약 (3줄 이내)
- Critical: N
- Major: N
- Minor/메모: N
- 불변 규칙 위반: 있음/없음

## Critical
- [파일:줄] 문제 / 왜 규칙 위반인지 / 재현·근거

## Major
- ...

## Minor · 개선 제안
- ...

## 확인 완료 (문제 없음)
- [ ] 섹터 캡 + financial alias
- [ ] 목표가 편입 차단
- [ ] 주간 B/E proposal-only
- [ ] 상대순위 확정 경로 제거
- [ ] 대체 API 라이브 제거 + 파서 유지
- [ ] oneshot scripts archive

## 보류 항목에 대한 의견 (수정 지시 금지)
- E (이중 앱): ...
- 30종 매직넘버: ...

## 확신도
- 전체: high/medium/low
- 저장소 미접근으로 못 본 것: ...
```

---

## Claude용 시작 프롬프트 (복붙)

```
첨부한 CLAUDE_REVIEW_BRIEF_20260718.md 와 RESULT 문서·핵심 파일을 읽고
「검수 미션」대로 독립 검수해 주세요.
코드를 수정하거나 리팩터 제안으로 범위를 넓히지 마세요.
보고 템플릿 형식으로만 답하세요.
불변 규칙 위반이 Critical입니다.
P2(E, 전체 pytest hang, 30종 매직넘버)는 수정 지시 없이 의견만.
```
