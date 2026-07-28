# target write 감사 추적성 개선 — 결과

> 명세: [`TARGET_WRITE_AUDIT_TRACEABILITY_FIX_SPEC.md`](TARGET_WRITE_AUDIT_TRACEABILITY_FIX_SPEC.md)  
> 근거: 2026-07-15 write = 원장 본인 승인 확인. 추적성만 보강 (권한·ALLOWED_WRITE_SOURCES 불변)

## 1. 구현

| ID | 내용 | 위치 |
|----|------|------|
| A | `write_material_change_count` + `user_op_guard_diff_rows` | `count_material_weight_changes` · `write_operational_target` audit; approval_log에도 기록. `changed_rows_after_write` **유지**(값=user_op sync diff) |
| B | UI 승인자 필수 | `target_approval_actions` — 공란 시 버튼 `disabled`, `approver or "human"` 제거 |
| C | writer_module 구분 | UI=`ui.target_approval_actions` · CLI=`scripts.apply_target_draft` · `apply_proposed_target(..., writer_module=)` |
| D | 성공 toast | `"반영 완료 — N종 가중치 변경"` (N=audit count) |

`apply_proposed_target` 반환: `TargetWriteResult` (기존 Path 반환 호출부는 side-effect only라 호환).

## 2. 검증

| # | 항목 | 결과 |
|---|------|------|
| 1 | material count | **원장 pass** — 백업 vs 현재 재계산 **21** 일치 |
| 2 | 승인자 필수 | **원장 pass** — disabled·human 제거 |
| 3 | writer_module | **원장 pass** — UI/CLI 각각 명시 |
| 4 | toast N종 | **원장 pass** — audit `write_material_change_count` |
| 금지 | ALLOWED sources 불변 | **원장 pass** |

**종결 (2026-07-15):** 원장 검증 완료. target write 추적성 건 종료.

## 3. 금지 준수

- 승인 단계 수/체크박스 구조 유지 (실명만 필수)  
- ALLOWED/FORBIDDEN sources 미변경  
- `changed_rows_after_write` 필드 유지  
- target CSV 스키마/값 자동 변경 없음
