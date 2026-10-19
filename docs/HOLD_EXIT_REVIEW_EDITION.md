# 보유·매도 Review 에디션 (병렬 실행)

> **일자:** 2026-10-08 · **상태:** v1 구현 (Phase 1–4 코어)  
> **기본 앱:** `alpha_dashboard.py` / `투자나침반.bat` — **변경 없이** 그대로 사용  
> **에디션:** `alpha_dashboard_hold_exit.py` / `투자나침반-hold-exit.bat` (포트 **8502**)

---

## 무엇이 다른가

| 항목 | 기본 v3 | 이 에디션 |
|------|---------|-----------|
| QVM·제안·target | 동일 | 동일 (순위·파일 자동 변경 없음) |
| 통합 신호 UI | 장부+차트 3층 | + **Data Gate / 보유 근거 / 허용 행동 / 트리거** |
| 품질 표시 | (없음) | **최종 제안** 목록을 Q↓·하케다카↓ 정렬 + 행마다 Q·하케다카·총점 |
| 제안 이탈 | 익절 스텝 즉시 반영 | **N주 히스테리시스** 후 교체 검토 |
| 월 Review | 분산 UI | **월말 보드** (교체·비중·가설·관찰) |
| 설정 | `alpha_system.yaml` | + `alpha_system/config/hold_exit_review.yaml` |

---

## 실행

```powershell
cd C:\Cursor\investment\investment-alpha-screener
.\투자나침반-hold-exit.bat
# 콘솔이 바로 닫히면 오류 확인:
.\run_ui_hold_exit.bat
```

브라우저: http://127.0.0.1:8502

---

## 코드 위치

- `alpha_system/hold_exit_review/` — 상태머신·이력·enrich·cue·월 보드·품질 정렬(`quality_board`)
- `alpha_system/ui/pages/portfolio_hold_exit.py` — 포트폴리오 페이지 래퍼
- `data/local/hold_exit_proposal_weeks.jsonl` — 주간 제안 스냅샷 (gitignore)

전체 로드맵: [`VALUE_HOLD_EXIT_UPGRADE_PLAN.md`](VALUE_HOLD_EXIT_UPGRADE_PLAN.md)

---

## 미구현 (계획서 Phase 5–6)

- A0/A1/A2 백테스트 스크립트
- 미국 13F / 달러 구루 (repo 밖)

기본 앱에 합치기 전에 이 에디션에서 운영·숫자(§4)를 확정하세요.
