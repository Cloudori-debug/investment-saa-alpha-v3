# target_write_audit (2026-07-15 03:53 UTC) — 조사 결과

> 요청: [`TARGET_WRITE_AUDIT_20260715_INVESTIGATION_REQUEST.md`](TARGET_WRITE_AUDIT_20260715_INVESTIGATION_REQUEST.md)  
> 범위: **조사만** (감사 필드 의미 설명. 코드 수정 없음)  
> 개정(2026-07-15): 원장 검증 반영 — **「UI 클릭 확정」 판정 철회**. UI vs `apply_target_draft --apply` 구분 한계를 §2·§5에 명시.

## 한 줄 결론

**스케줄/파이프라인 자동 write는 아니다.** `apply_proposed_target` → `approval_bridge`가 **의도적 트리거**로 돌았고, 가중치는 실변경(21종).  
다만 로그만으로 **대시보드 클릭 vs 터미널 `--apply`**를 100% 단정할 수 없다.  
`changed_rows_after_write: 0`은 write 행수가 아니라 **승인 후 user↔op 가드 diff**(sync 후 거의 항상 0).

## 1. hash는 바뀌고 changed_rows=0인 이유

| 필드 | 의미 (코드) |
|------|-------------|
| `target_hash_before` / `after` | `ticker`+`target_weight` 정규화 집합 SHA256 ([`_content_hash`](../src/alpha/target_portfolio_guard.py)) |
| `changed_rows_after_write` | write **직후** `evaluate_target_guard` → user_target vs operational 불일치 행 수 |

승인 경로 sync 후 `changed_rows_after_write=0`은 **정상**. 실변경 행수는 pre_write 백업 vs 현재, 또는 approval_log `change_count`로 볼 것.

### 실제 weight 변화 (백업 대조 · 원장 재확인)

- 백업: `data/backups/target_portfolio.20260715T035329Z.pre_write.bak.csv` (`cef58671…`)
- 이후: `data/target_portfolio.csv` (`26035b3b…`)
- 예: KT 5.89→4.99, 코웨이 5.89→4.99, 하이닉스 2.95→2.50, **036530 신규 1.28**, 전 portfolio 재정규화
- kr_alpha 합 ≈ **23.63 → 21.28** (로그 Compass 예산 20.7% 스케일과 정합)

## 2. 트리거 출처 — UI vs CLI (한계)

공통 경로:

```text
apply_proposed_target(approved_by_user=True 기본)
  → write_operational_target(source="approval_bridge", …)
```

| 진입점 | `approved_by` 기본 | `write_reason` (write_reason 미지정 시) |
|--------|-------------------|----------------------------------------|
| UI [`target_approval_actions`](../src/ui/target_approval_actions.py) | 텍스트 빈칸 → `"human"` | `alpha_proposal_approved_by=human` |
| CLI [`scripts/apply_target_draft.py --apply`](../scripts/apply_target_draft.py) | argparse 기본 `"cli"` | `alpha_proposal_approved_by=cli` |
| CLI `--approved-by human` | `"human"` | **UI와 동일 문자열** |
| `resync_kr_alpha_bands` / `align_071050_*` | (명시 reason) | `band_resync` / `satellite_cap_alignment` — **이번 이벤트와 불일치** |

오늘 로그: `write_reason=alpha_proposal_approved_by=human`, approval_log `approved_by=human`.  
→ **스크립트 기본값(`cli`)는 아님.** UI(승인란 공란) 또는 `apply_target_draft.py --apply --approved-by human` 가능.  
`writer_module`도 둘 다 `target_bridge.apply_proposed_target`이라 **파일만으로는 UI/CLI 최종 확정 불가**.

자동 실행 배제(원장·코드 재확인):

- `daily_pipeline` / `실행.bat`은 이 write 경로 **미호출**
- 7/13×3 · 7/14×1 · 7/15×1 동일 패턴 → 사람이 UI든 CLI든 **반복 트리거**한 해석이 가장 자연스러움

**원장 확인 요청:** 해당 기간에 「알파 → Target 승인」 클릭 또는 `apply_target_draft.py --apply` 실행 기억이 있는지.  
- 있으면 → 감사 개선(§6)으로 재발 방지하면 충분  
- 없으면 → 재조사(터미널 history·다른 머신·누가 `--approved-by human`을 썼는지)

## 3. proposal vs 현재 target

조사 시점 proposal hash ≠ operational — 승인 이후 proposal 재생성으로 볼 수 있음.

## 4. CAUTION 재분류

CAUTION 파이프라인은 approval_bridge **미호출**. Compass 20.7%는 TAA 반영 proposal을 **누군가 승인한 결과**와 숫자대만 맞음.

## 5. 판정 (수정)

| 가설 | 판정 |
|------|------|
| 포맷만 바뀌어 hash 변경 | **기각** — 21종 weight 실변경 |
| 스케줄/파이프라인 자동 write | **기각** |
| **UI 클릭으로 확정** | **철회** — CLI `--approved-by human`과 로그 동일 가능 |
| 의도적 `apply_proposed_target` (UI 또는 CLI) | **채택** (가장 유력) |
| CAUTION이 target 직접 write | **기각** |
| 감사 `changed_rows=0` 필드 오해 | **채택** (사실관계) |

## 6. 개선 제안 (별도 스펙 · 미구현)

1. 감사에 `write_material_change_count`(before/after 실변경) 추가; `changed_rows_after_write` → `user_op_guard_diff_rows`로 문서화·개명  
2. UI 승인자 빈 `"human"` 금지(실명/이니셜 필수)  
3. `writer_module`을 UI=`ui.target_approval_actions` / CLI=`scripts.apply_target_draft`로 **명시 전달** (지금은 둘 다 `apply_proposed_target`)  
4. (선택) 승인 직후 toast에 backup diff 행수 표시

원장 기억 확인 후 §6 경량 SPEC → 구현 여부 결정.
