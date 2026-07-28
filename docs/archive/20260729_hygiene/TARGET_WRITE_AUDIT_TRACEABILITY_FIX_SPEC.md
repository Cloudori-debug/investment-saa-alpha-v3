# target write 감사 추적성 개선 — 명세서 (경량)

> 근거: `TARGET_WRITE_AUDIT_20260715_INVESTIGATION_RESULT.md` §6 — 오늘 write는 동준님 본인의 정상 승인으로 확인됨(재조사 종결). 다만 조사 과정에서 감사 로그만으로는 **UI 클릭 vs CLI 실행을 구분할 수 없고**, `changed_rows_after_write` 필드명이 **오해를 유발**한다는 두 가지 설계 약점이 드러났음. 재발 시 즉시 판별 가능하도록 감사 필드를 보강.
> 원칙: **감사·표시 개선만.** 승인 로직(누가 승인 가능한지, 몇 단계 승인인지)·write 권한 자체는 변경 없음. `ALLOWED_WRITE_SOURCES`(`approval_bridge`/`restore_from_user_target`/`manual_admin_override`) 불변.

## 1. 범위

### A. `write_material_change_count` 추가
- `apply_proposed_target()` write 시점에 pre-write 백업(`data/backups/*.pre_write.bak.csv`) vs 신규 rows를 `_content_hash`와 동일한 (ticker, weight) 집합 기준으로 비교, **실제로 값이 달라진 ticker 수**를 계산해 audit 엔트리(`target_write_audit.jsonl`)와 `approval_log.jsonl`에 `write_material_change_count` 필드로 기록.
- 기존 `changed_rows_after_write`는 **삭제하지 않고 유지** (하위호환), 단 필드 설명 주석/문서를 `user_op_guard_diff_rows`(승인 직후 user_target↔operational 가드 diff, 통상 0)로 명확화.

### B. 승인자 실명/이니셜 필수화 (UI)
- `src/ui/target_approval_actions.py`: 승인 버튼 활성화 조건에 "승인자 이름/이니셜 입력" 텍스트 필드를 추가하고, 공란이면 버튼 비활성 또는 경고. `approved_by`에 빈 문자열 대신 입력값 전달 (기본값 `"human"` 자동 대입 제거).
- CLI(`apply_target_draft.py`)는 이미 `--approved-by` 인자가 있으므로 UI만 보강.

### C. `writer_module` UI/CLI 구분
- `apply_proposed_target()` 시그니처에 `writer_module: str | None = None` 파라미터 추가(기본값 없으면 기존처럼 `"target_bridge.apply_proposed_target"`).
- `target_approval_actions.py` 호출부: `writer_module="ui.target_approval_actions"` 명시 전달.
- `scripts/apply_target_draft.py` 호출부: `writer_module="scripts.apply_target_draft"` 명시 전달.
- `resync_kr_alpha_bands.py`/`align_071050_satellite_cap.py`는 이미 `write_reason`으로 구분되므로 우선순위 낮음(선택).

### D. (선택) 승인 직후 toast에 실변경 건수 표시
- UI 승인 성공 메시지를 `"target_portfolio.csv 반영 완료"` → `"target_portfolio.csv 반영 완료 — N종 가중치 변경"`으로 보강 (N = write_material_change_count).

## 2. 절대 금지
- 승인 권한/단계(현재: 체크박스 동의 + 버튼 1회) 자체를 강화하거나 약화하는 로직 변경 금지 — 이번 스펙은 **기록 추적성**만 다룸
- `ALLOWED_WRITE_SOURCES`/`FORBIDDEN_WRITE_SOURCES` 목록 변경 금지
- 기존 `changed_rows_after_write` 필드 제거 금지 (하위호환 — 기존 파서/로그 참조 깨짐 방지)
- target_portfolio.csv 자체의 값/스키마 변경 없음

## 3. 검증 요청
1. 오늘(7/15) 사례를 재현: 임의 proposal로 dry-run write 후 `write_material_change_count`가 실제 변경 ticker 수(예: 21)와 일치하는지
2. UI에서 승인자 이름 미입력 시 승인 버튼이 막히는지, 입력 시 `approved_by`에 그 값이 그대로 기록되는지
3. UI 경로와 CLI 경로 각각 실행 후 `writer_module` 값이 `ui.target_approval_actions` / `scripts.apply_target_draft`로 다르게 찍히는지
4. 기존 테스트(`test_target_bridge.py`, `test_target_write_audit.py`, `test_target_approval_ui.py`) 전부 통과 — 필드 추가가 기존 스키마를 깨지 않는지
