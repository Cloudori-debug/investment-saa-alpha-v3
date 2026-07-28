# 하이브리드 전환 전체 반영 메커니즘 — RESULT

> SPEC: [`KR_ALPHA_HYBRID_FULL_APPLY_MECHANISM_SPEC.md`](KR_ALPHA_HYBRID_FULL_APPLY_MECHANISM_SPEC.md)  
> 선행: 시나리오 B · 정책 하한 한시 예외  
> 원칙: **옵션 1 스크립트 + preview만**. `--apply`는 원장 명시 실행 전 **미사용**.

## 한줄 결론

§0 진단(kr_alpha-only) **재확인 일치**. 옵션 1로 `scripts/apply_kr_alpha_hybrid_scenario_b.py`를 추가했고, preview는 시나리오 B 숫자와 **일치**. `target_portfolio.csv`는 이 작업으로 **미변경**.

---

## 1. 진단 재확인 (Cursor)

| 주장 | 코드/파일 확인 |
|---|---|
| draft가 구버전 | `alpha_portfolio/data/output/target_draft.csv` mtime **2026-07-09**, KT/코웨이 7% 등 — 하이브리드 세션 산출물 아님 |
| `merge_target_draft` kr_alpha만 교체 | `src/alpha/target_draft_bridge.py`: `non_kr = [… if r.asset_group != "kr_alpha"]` 후 `rows = non_kr + new_kr` |
| UI도 kr_alpha-only | `src/ui/target_draft_workflow.py` 문구: "kr_alpha 목표만 교체 · ETF·현금 등 다른 자산군은 유지" |
| income_alt 경로 없음 | approval_bridge/`apply_target_draft.py`는 위 merge만 사용 → **시나리오 B 전체 반영 불가** |

→ 원장 진단 **정확**.

---

## 2. 선택: 옵션 1 (`manual_admin_override`)

| 항목 | 내용 |
|---|---|
| 이유 | 1회성 그룹 간 이동 · 기존 kr_alpha-only UI/테스트 **비침습** · `ALLOWED_WRITE_SOURCES`에 이미 존재 · `approved_by_user=True` 게이트 approval_bridge와 동일 |
| 옵션 2 | 구조 확장은 회귀 범위 큼 → **이번 보류**(필요 시 별도 스펙) |

스크립트: [`scripts/apply_kr_alpha_hybrid_scenario_b.py`](../scripts/apply_kr_alpha_hybrid_scenario_b.py)

- 기본 = **preview** (write 없음)
- `--apply`는 `--approved-by <실명>` 필수(빈 값/`cli` 거부) → 그제야 `approved_by_user=True`
- `source="manual_admin_override"`, `reason="KR_ALPHA_HYBRID_TRANSITION scenario B; approved_by=…"`
- `writer_module="scripts.apply_kr_alpha_hybrid_scenario_b"`
- 기존 `merge_target_draft` / Target 승인 UI **미수정**

---

## 3. Preview 실행 결과 (write 없음)

```
Group sums (before → after):
  cash_short_bond: 32.17 → 32.17
  global_beta:     25.04 → 25.04
  hedge_alt:        7.15 → 7.15
  income_alt:      14.36 → 29.64
  kr_alpha:        21.28 → 6.00
  TOTAL:           100.00 → 100.00

Ticker diffs (요약):
  kr_alpha keep: 005830 3.81→3.50, 005440 1.15→2.50
  kr_alpha remove: 030200,021240,006040,271560,036530,000660 (+보유분이지만 target에 없던 쿠쿠·그린푸드는 원래 행 없음)
  income_alt: 161510 3.59→11.79, +279530 7.08
  domestic_beta: 없음

Validation: OK (kr_alpha=6.00, income_alt=29.64, domestic_beta=0, total=100)
```

---

## 4. 실제 적용 커맨드 (원장 실행용 — 아직 실행하지 말 것)

저장소 루트 `C:\Cursor\investment-saa-alpha`에서:

```bat
python scripts/apply_kr_alpha_hybrid_scenario_b.py
```

위 preview로 숫자 재확인 후:

```bat
python scripts/apply_kr_alpha_hybrid_scenario_b.py --apply --approved-by <원장이름>
```

예: `--approved-by dongjun`

적용 시 동작: `data/target_portfolio.csv` + `user_target_portfolio.csv` 동기화, `data/backups/target_portfolio.*.pre_write.bak.csv` 백업, audit 로그. **매매 실행은 하지 않음**(목표 파일만).

---

## 5. 절대 금지 준수

| 항목 | 상태 |
|---|---|
| 이 스펙에서 `--apply` 실행 | **하지 않음** |
| `approved_by_user=True` 하드코딩 게이트 우회 | **거부**(이름 필수) |
| `kr_alpha_exit_targets.yaml` 변경 | **하지 않음** |
| `merge_target_draft` / UI 로직 변경 | **하지 않음** |

참고: `git diff`에 `target_portfolio.csv`가 보이더라도 mtime·내용 기준 **이전 세션 잔여**이며, 본 스크립트 preview는 write 경로를 타지 않음.

## 6. 검증 체크리스트

1. §0 진단 재확인: **완료**  
2. 옵션 1 + 근거: **완료**  
3. preview = 시나리오 B 숫자: **완료**  
4. target 실변경 없음(본 작업): **준수**  
5. 적용 커맨드 문서화: **§4**
