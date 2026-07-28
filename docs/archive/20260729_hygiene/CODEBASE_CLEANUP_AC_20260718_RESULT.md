# Cleanup A+C — 죽은 UI / 상대순위 슬라이더 제거 (2026-07-18)

> **범위:** 안정판 `stable-20260718-final-selection` 이후 1차 정리  
> **방식:** archive 이동 (완전 삭제 아님)  
> **코드 루트:** `C:\Cursor\investment-saa-alpha`

---

## C — 정책 정합 (필수)

| 항목 | 내용 |
|------|------|
| 문제 | 체크리스트 `score_cutoff` 패널에 **상대순위(상위 N→컷 파생)** 슬라이더가 남아 포트폴리오의 **절대 cutoff → 5~8** 철학과 충돌 |
| 조치 | `action_panels._panel_checklist_cutoff`에서 상대순위 UI·`method=relative_rank_slider` 확정 경로 제거. 상관 리포트 생성은 유지. 확정은 **포트폴리오 화면으로 이동**만 제공 |
| 카피 | `docs/UI_COPY.md`: `cutoff_relative_help` → `cutoff_absolute_help`. `data_stale`의 「설정·이벤트」→「결재함(또는 홈)」 |

단일 SoT: 절대 컷오프·편입 수 확정은 `alpha_system/ui/pages/portfolio.py`만.

---

## A — 죽은 코드 archive

| 원본 | archive | 근거 |
|------|---------|------|
| `alpha_system/ui/pages/cecs_scoring.py` | `archive/20260718_dead_ui/` | nav 리다이렉트만, 호출 0 |
| `alpha_system/ui/pages/settings.py` | 동일 | `render_events` alias, 호출 0 |
| `events.render_events()` | 삭제(함수만) | settings 전용 소비자였음. `_render_*` 헬퍼는 결재함에서 계속 사용 |
| `scripts/debug_kosis_cpi.py` 등 5개 | `archive/20260718_debug_scripts/` | 일회성 프로브, 운영 참조 0 |

디버그 스크립트 5개: `debug_kosis_cpi`, `debug_kosis_cpi_rows`, `probe_kosis_tblid`, `benchmark_p16_diagnostics`, `verify_prices_history_impact`.

---

## 보류 (다음 라운드)

- **B** 대체된 CECS AI 단독 리포트 API + 테스트 개정
- **D** 일회성 target-write 스크립트 archive
- **E** `app.py` vs `alpha_dashboard.py` 중복

---

## 검증

```powershell
python -m pytest -q -p no:cacheprovider `
  tests/test_action_panels.py `
  tests/test_dashboard_nav_journal.py `
  tests/test_home_pipeline.py `
  tests/test_pre_launch_and_copy.py `
  tests/test_select_eligible_sector_cap.py
```

기대: 전부 pass. `relative_rank_slider` 문자열은 운영 코드에 없어야 함(저널 이력 JSONL은 과거 기록으로 유지).
