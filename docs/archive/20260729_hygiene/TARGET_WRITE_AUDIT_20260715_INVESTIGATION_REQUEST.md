# target_write_audit 원인 확인 요청 (2026-07-15)

> 범위: 조사·설명만. 코드 수정 없음 (원인이 버그로 밝혀지면 별도 스펙으로 진행).

## 발견 사실

`ai_cross_validation_20260715_1315.zip` → `export_bundle_validation.json` → `target_write_audit`:

```json
{
  "timestamp": "2026-07-15T03:53:29.611320+00:00",
  "run_id": "2026-07-15T12:08:29+09:00",
  "target_write_source": "approval_bridge",
  "target_write_reason": "alpha_proposal_approved_by=human",
  "target_write_allowed": true,
  "writer_module": "target_bridge.apply_proposed_target",
  "approved_by_user": true,
  "proposal_source_id": "outputs/proposals/target_portfolio_proposed.csv",
  "target_path": "data/target_portfolio.csv",
  "target_hash_before": "cef58671...",
  "target_hash_after": "26035b3b...",
  "changed_rows_after_write": 0
}
```

- `target_bridge.apply_proposed_target`가 오늘 03:53 UTC에 **사람 승인(approved_by_user=true)** 경로로 실행됨
- 그런데 `changed_rows_after_write: 0` — 실제 행 변경은 없음
- 동준님은 오늘 알파 제안을 승인한 기억이 없음

## 확인 요청

1. `target_hash_before`(`cef58671...`)와 `target_hash_after`(`26035b3b...`)가 다른데 `changed_rows=0`인 이유
   - 포맷/공백/컬럼 순서 변경만으로 hash가 바뀌고 실제 값은 동일했는지
   - 아니면 이전(어제 CAUTION 재분류 관련 커밋)에 이미 반영된 값이 오늘 재기록되며 hash만 새로 계산된 것인지
2. `approved_by_user: true`가 어떤 이벤트에서 세팅됐는지 — UI에서 실제 클릭 승인이 있었는지, 아니면 파이프라인 내부에서 이전 승인을 재사용/재실행하는 경로가 있는지
3. `outputs/proposals/target_portfolio_proposed.csv`의 현재 내용과 `data/target_portfolio.csv`가 실제로 동일한지 diff 확인
4. 이 write가 어제(2026-07-14) 진행한 REGIME_CAUTION_RECLASSIFICATION_SPEC 적용과 관련된 재실행인지, 아니면 별개의 알파 후보 승인 경로인지

## 산출물 요청

- 원인 설명 (RESULT.md 또는 채팅 요약)
- `target_bridge.apply_proposed_target` 호출 스택/트리거 지점 (스케줄러 자동 실행인지, UI 승인 버튼 경로인지)
- 결론이 "정상 동작(재확인성 write, no-op)"이면 그 근거를, "의도치 않은 자동 승인"이면 재발 방지 방안을 제시
