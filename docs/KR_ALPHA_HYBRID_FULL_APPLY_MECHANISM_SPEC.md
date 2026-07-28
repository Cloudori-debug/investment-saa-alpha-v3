# 하이브리드 전환(시나리오 B) 전체 반영 메커니즘 — 실행 명세서

> 선행: [`KR_ALPHA_HYBRID_TRANSITION_RESULT.md`](KR_ALPHA_HYBRID_TRANSITION_RESULT.md)(시나리오 B) · [`KR_ALPHA_POLICY_FLOOR_TEMP_EXCEPTION_RESULT.md`](KR_ALPHA_POLICY_FLOOR_TEMP_EXCEPTION_RESULT.md)
> 원장이 실제 프로그램을 실행해봤으나 "외관이 변한 게 없다"고 확인 — 원인 진단 완료(아래), 이 스펙은 **해결 방법 설계까지만**.

## 0. 원인 진단 (원장이 직접 코드로 확인함 — Cursor는 이 진단이 맞는지만 재확인)

1. `alpha_portfolio/data/output/target_draft.csv`(실제 approval_bridge가 읽는 파일)는 **2026-07-09 날짜의 구버전**(KT 7%·코웨이 7% 등) — 이번 하이브리드 전환과 무관. 이번 세션 산출물은 전부 `docs/*.md` 문서였고, 시스템이 실제로 읽는 draft 파일은 한 번도 갱신되지 않음.
2. **더 근본적 문제**: `src/alpha/target_draft_bridge.py::merge_target_draft()`가 `non_kr = [r for r in current if r.asset_group != "kr_alpha"]`로 **kr_alpha 이외 그룹은 그대로 통과**시키고, draft로 교체되는 건 kr_alpha 행뿐. `src/ui/target_draft_workflow.py`도 "kr_alpha 목표만 교체 · ETF·현금 등 다른 자산군은 유지"라고 명시(주석·UI 문구 확인).
3. 즉 이 approval_bridge/Target 승인 UI 경로는 **kr_alpha 종목 교체 전용**으로 설계돼 있어, 시나리오 B의 income_alt 증액분(161510 3.59→11.79, 279530 신규 7.08)을 반영할 경로가 **존재하지 않음**.

## 1. 요구사항

시나리오 B는 kr_alpha(그룹 내 종목 교체+축소)와 income_alt(그룹 간 비중 이동)를 **동시에** 반영해야 함. 아래 중 하나로 해결책을 설계·제안할 것.

### 옵션 1 — `manual_admin_override` write source 활용 (권장 후보)

`src/alpha/target_write_audit.py`의 `ALLOWED_WRITE_SOURCES`에 `manual_admin_override`가 이미 존재하며, `approved_by_user=True` 요구 조건도 `approval_bridge`와 동일함(93-95행 확인). 이 경로로:

1. 시나리오 B 전체 목표(kr_alpha 6% + income_alt 29.64% + 나머지 그룹 유지)를 반영한 **전체 `TargetRow` 리스트**를 구성하는 스크립트/함수를 신규 작성(`apply_target_draft.py`류의 CLI 패턴 참고).
2. `write_operational_target(data_dir, rows, source="manual_admin_override", approved_by_user=True, approved_by=<원장 이름>, writer_module=<신규 모듈명>, reason="KR_ALPHA_HYBRID_TRANSITION scenario B")` 호출.
3. **--apply 플래그 없이는 diff/미리보기만 출력**하고, 실제 write는 원장이 명시적으로 실행 명령을 내릴 때만 — 기존 `apply_target_draft.py`의 preview/apply 이원 구조와 동일 패턴 유지.

### 옵션 2 — `target_draft_bridge`를 다중 그룹 지원으로 확장

`merge_target_draft()`가 kr_alpha 외 그룹도 draft에서 교체 가능하도록 일반화(예: draft.csv에 `asset_group` 컬럼 기준으로 여러 그룹을 함께 교체). 장점: 기존 UI("Target 승인" 탭)를 그대로 재사용 가능. 단점: 기존 kr_alpha-only 로직/테스트에 영향 범위가 넓어 회귀 위험 있음 — 신중 검토.

### 판단 기준

- 이번 1회성 전환이면 **옵션 1**(영향 범위 작음, 기존 UI/로직 안 건드림)을 권장.
- 앞으로도 그룹 간 비중 이동이 반복될 것 같으면 **옵션 2**(구조적 해결)를 고려하되, 별도 스펙으로 분리.

**이 스펙에서는 옵션 1로 진행**(빠르고 안전). 옵션 2가 필요하다고 판단되면 그 근거만 보고하고 별도 스펙 요청.

## 2. 절대 금지

- 어떤 옵션이든, **실제 파일 쓰기(--apply)는 원장의 명시적 실행 없이는 발생하지 않아야 함** — 이 스펙에서 자동 적용 금지.
- `write_operational_target` 호출 시 `approved_by_user=True`가 실제로 사람 승인 시점에만 True가 되도록(하드코딩된 True로 게이트를 무력화하지 않을 것).
- kr_alpha_exit_targets.yaml 등 이번 범위 밖 파일 임의 변경 금지.

## 3. 산출물

- `scripts/apply_kr_alpha_hybrid_scenario_b.py`(가칭) — preview(기본)/--apply 이원 구조, 시나리오 B 전체 target 반영.
- `docs/KR_ALPHA_HYBRID_FULL_APPLY_MECHANISM_RESULT.md` — 진단 재확인, 선택한 옵션과 이유, 스크립트 preview 실행 결과(diff만, 실제 적용 안 함), 실제 적용 시 실행할 정확한 커맨드(원장이 나중에 직접 실행).

## 4. 검증 체크리스트

1. §0 진단(kr_alpha-only 설계)이 Cursor 쪽에서도 재확인됐는지.
2. 선택한 옵션과 근거가 타당한지.
3. preview 실행 결과가 시나리오 B 숫자(kr_alpha 6%, 161510 11.79%, 279530 7.08%, domestic_beta 없음, 합 100%)와 정확히 일치하는지.
4. 이 스펙 작업으로 `target_portfolio.csv`가 실제로 변경되지 않았는지(git diff).
5. 실제 적용 커맨드가 명확히 문서화됐는지(원장이 나중에 그대로 실행 가능하도록).
