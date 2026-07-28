# 익절 목표상태 마커 — 결과

> 명세: [`EXIT_TARGET_STATUS_MARKER_SPEC.md`](EXIT_TARGET_STATUS_MARKER_SPEC.md)  
> 원칙: **표시 순서·아이콘만** — 익절 계산 로직 미변경

## 1. 구현

| 위치 | 변경 |
|------|------|
| 대시보드 | `prepare_take_profit_board_view` — 컬럼 `ticker, name, 목표상태, …` (`targets_missing` 원본 컬럼 제거). 상단 배너 N/총 미설정 |
| 워크시트 | `WORKSHEET_COLUMNS`에 `목표상태`를 name 다음으로; `has_existing_target` bool 컬럼 → 아이콘 문자열. MD 배너 동일 |
| 공통 | `exit_target_status_label` / `STATUS_MISSING`·`STATUS_SET` (`exit_target_worksheet.py`) |

- `⚠️ 목표 미설정` / `✅ 목표 설정됨`
- `target_roe_min` 등 4칸 **여전히 공란**

## 2. 소비자 grep

`kr_alpha_exit_target_worksheet.csv` / `has_existing_target` 컬럼명을 읽는 **다른 런타임 코드 없음** (테스트·문서만). 컬럼명 교체 안전.

## 3. 검증

| # | 결과 |
|---|------|
| 1 | **원장 pass** — 대시보드 name 다음=목표상태; `targets_missing` 원본 제거 |
| 2 | **원장 pass** — CSV 헤더·행 `⚠️ 목표 미설정` 직접 확인 |
| 3 | **원장 pass** — target_* 4칸 공란 |
| 4 | **원장 pass** — 타 런타임 소비자 없음 |

**종결 (2026-07-15):** 원장 검증 완료. 목표상태 마커 건 종료.
