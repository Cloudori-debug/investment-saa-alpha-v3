# 대시보드 자동 저널 감사 — 빠진 기록 조사·보강

조사일: 2026-07-16  
범위: `alpha_system` 대시보드 경로 (`load_context`는 `journal=False`로 평가)

## 이미 기록되던 것

| 사건 | 경로 |
|------|------|
| T2 / 논지훼손 / 취소 | 이벤트 입력 UI → `append_record` (수동 2단계 유지) |
| go-live 성공 | `GO_LIVE_DECLARE` |
| 목표가 수정·재량 청산 | 저널 UI |
| `attempt_execute` 차단/집행 | `journal=True` 시 `WARN_BLOCKED` / `EXECUTE` |
| 스왑 후보 | `evaluate_swap_observe(journal=True)` |
| entry evaluate 내부 액션 | `journal=True`일 때만 (대시보드는 False) |

## 미기록 → 이번에 추가

| 사건 | action_kind | 구현 |
|------|-------------|------|
| 트랜치 상태 전이 | `TRANCHE_STATE_TRANSITION` | `auto_journal.sync_system_journal` |
| 트리거 발화/해제 | `TRIGGER_FIRED` / `TRIGGER_CLEARED` | 동일 (runtime 스냅샷 대비) |
| 하드 룰 차단 (평가 액션) | `HARD_RULE_BLOCK` | 동일 |
| cap 임박 / 초과 | `CAP_WARN` / `CAP_OVER` | 동일 (톤 변화 시) |
| 데이터 갱신 성공/실패 | `DATA_REFRESH_OK` / `DATA_REFRESH_FAIL` | 이벤트 입력 갱신 버튼 |
| go-live 체크리스트 차단 | `GO_LIVE_ATTEMPT_BLOCKED` | go-live 시도 시 |

중복 방지: `RuntimeState.journaled_*` 필드에 직전 스냅샷을 저장.

## 자동화하지 않는 것 (의도)

- T2 이벤트·논지 훼손 수동 입력 — 2단계 확인 유지. 딥링크로 폼 도달만 축소.

## 저널 필터 카테고리

전체 / 집행·전이 / 경고 / 차단 / 재량 / 데이터 / 입력  
(`journal_filters.categorize`)
