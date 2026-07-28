# kr_alpha min/max 밴드 드리프트 — 수정 결과

> 명세: `docs/TARGET_MINMAX_BAND_FIX_SPEC.md`  
> 구성: **8종목 유지 (071050 포함)** · policy_cap / execution_scope / throttle 미변경

## 1. 구현 요약 (A → B → C)

### A. 예산 스케일 시 밴드 동반 갱신
- `src/alpha/target_bridge.py`: `scale_kr_alpha_row_to_budget()` — `propose_target_changes()`의 `kr_alpha_budget` 스케일에서 **target·min·max 동일 factor**
- `src/alpha/target_draft_bridge.py`: `merge_target_draft()` 동일 결함 수정

### B. 신규 add 경로
- `resolve_add_candidate()`: 기본 1.0/4.0 폐기 → `alpha_portfolio` `compute_bands()` (+ 제안 target이 밴드 안에 들어가도록 정합 클램프)
- `default_add_candidates()`: **WATCH / BLOCK_NEW_BUY / NO_NEW** 제외

### C. live 1회 재동기화
- `build_band_resync_proposal()` + `scripts/resync_kr_alpha_bands.py --apply`
- 경로: draft 종목은 **draft 밴드 × (live_tw/draft_tw)**; draft 밖(071050)은 **compute_bands**
- 반영: `apply_proposed_target(..., write_reason="band_resync")` → `outputs/target_write_audit.jsonl`
- CSV 직접 편집 없음 · `user_target_portfolio.csv` 동기화됨

## 2. 단위 테스트
`tests/test_target_bridge.py` — **12 passed** (신규: budget 스케일 min/max, WATCH 필터, compute_bands add)

## 3. 재동기화 전/후 diff (kr_alpha)

원본(세션 전 `target_portfolio.20260711T021107Z.pre_write.bak.csv`) 대비 최종:

| 티커 | 전 (target / min / max) | 후 | 비고 |
|------|-------------------------|-----|------|
| 071050 | 5.56 / 1.0 / 4.0 | 5.56 / **0.0 / 5.56** | draft 없음 → compute_bands |
| 030200 | 4.07 / 5.36 / 16.05 | 4.07 / **3.12 / 9.33** | draft factor |
| 021240 | 4.07 / 5.36 / 16.05 | 4.07 / **3.12 / 9.33** | draft factor |
| 005830 | 3.11 / 5.36 / 16.05 | 3.11 / **3.11 / 9.31** | draft factor |
| 000660 | 2.02 / 0.0 / 10.71 | 2.02 / **0.0 / 6.16** | draft factor |
| 006040 | 1.04 / 1.38 / 4.13 | 1.04 / **0.8 / 2.39** | draft factor |
| 271560 | 1.04 / 1.38 / 4.13 | 1.04 / **0.8 / 2.39** | draft factor |
| 005440 | 0.94 / 0.81 / 2.42 | 0.94 / **0.47 / 1.4** | draft factor |

**부수 수정:** 초기 decompose 경로가 ETF 밴드까지 스케일한 부작용을, 동일 백업의 non-kr 밴드로 `band_resync` 감사 쓰기로 복구함. 최종 `build_band_resync_proposal()`는 **kr_alpha만** 갱신.

## 4. 검증

| 항목 | 결과 |
|------|------|
| `target outside min/max band` | **6건 → 0건** |
| `validate_inputs` / `input_validation_gate` | **YELLOW → GREEN** |
| ETF 등 non-kr 밴드 | 세션 전 백업과 일치 (예: 360750 8.91/16.55) |
| `target_write_reason` | `band_resync` (감사 로그) |
| operational hash 불변 | 정상 — `_content_hash`는 **ticker+target_weight만** 포함 (밴드만 바꾼 쓰기) |
| `portfolio_gate` / `data_gate` / 매수 | 로컬에 `final_execution_decision.json` 없음. **policy_cap(~2026-09-24)이 풀리기 전 YELLOW 유지 예상** — 이번 수정 실패가 아님 |

## 5. 재실행

```powershell
cd C:\Cursor\investment-saa-alpha
$env:PYTHONPATH='.'
python -m pytest tests/test_target_bridge.py -q
python scripts/resync_kr_alpha_bands.py          # dry-run
# python scripts/resync_kr_alpha_bands.py --apply  # 이미 적용됨
```
