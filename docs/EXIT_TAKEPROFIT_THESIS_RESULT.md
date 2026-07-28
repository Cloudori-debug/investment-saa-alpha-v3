# 익절(A/B) · 테제 훼손 — 1차 구현 결과 (가시성)

> 명세: [`EXIT_TAKEPROFIT_THESIS_SPEC.md`](EXIT_TAKEPROFIT_THESIS_SPEC.md) §7 실행 승인 2026-07-15  
> 범위: **Review-only** — `target_portfolio.csv` 미변경, 매매 실행 없음, v2 shadow 미병합

## 1. 구현

| 항목 | 위치 |
|------|------|
| 순수 평가 | `src/alpha/take_profit_thesis.py` — `assess_take_profit`, `assess_thesis_break`, `resolve_partial_frac_from_strength`, `apply_momentum_counter_check`, `load_exit_targets` |
| 보드 표시 | `src/alpha/alpha_signal_board.py` — `exit_leg`, `targets_missing`, `trim_source_tag`, `tp_*`, `momentum_override_applied`; trim/exit 문구에 출처 태그 |
| 목표가 스키마 | `data/kr_alpha_exit_targets.yaml` — `tickers: {}` (빈 상태) |
| 테스트 | `tests/test_take_profit_thesis.py` |

## 2. 검증 (§6 대응)

| # | 항목 | 결과 |
|---|------|------|
| 1–3 | TP-A / TP-B / BOTH | 단위 테스트 pass |
| 4 | TB Exit 우선 | `assess_thesis_break` TB-01→Exit (보드 action_state는 기존 hard flag 경로 유지) |
| 5 | target CSV 미기록 | 본 모듈·보드가 target write 경로 호출 안 함 |
| 7 | 계단 70/80/90 | pass |
| 8 | “확률” 등 금지 문자열 | 출력 blob assert |
| 9–10 | 모멘텀 카운터체크 | VAL 하향·FUND 미적용·rationale 포함 |

기존 `tests/test_alpha_signal_board.py` · `test_take_profit_thesis.py` 회귀 확인.

## 3. 금지 준수

- target 자동 감액 없음  
- Soft/Hard yaml ID 미변경  
- alpha_v2 `trim_watch` 미흡수 (공존; 태그 `trim:TP-*` vs `trim:score`)  
- signal_strength를 확률로 라벨링하지 않음  

## 4. 운영 다음 스텝

- 보유 kr_alpha에 목표가 점진 기입 (`kr_alpha_exit_targets.yaml`)  
- Claude/원장 독립 검증 후 2차(실행·승인 UI 연동)는 **별도 승인**
