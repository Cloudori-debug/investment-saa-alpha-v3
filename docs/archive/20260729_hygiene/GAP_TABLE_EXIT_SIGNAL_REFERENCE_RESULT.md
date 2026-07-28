# Target 승인 되돌리기 + Gap 표 익절 참고 — 결과

> SPEC: [`GAP_TABLE_EXIT_SIGNAL_REFERENCE_SPEC.md`](GAP_TABLE_EXIT_SIGNAL_REFERENCE_SPEC.md)  
> 원칙: **표시만** — 계산·Gap 수치·승인 버튼 변경 없음

## 1. 변경

| 항목 | 내용 |
|------|------|
| 되돌리기 | Target 승인 탭·⑥ target_draft 워크플로의 `render_take_profit_signals` 호출 **제거** |
| 유지 | 알파 → **보유 리뷰** 상세 익절 신호강도 표 |
| Gap | [`src/ui/portfolio_panel.py`](../src/ui/portfolio_panel.py) — `enrich_gap_with_exit_status`로 **익절상태** 컬럼(gap 다음) |

### 익절상태 표기

| 조건 | 표시 |
|------|------|
| board에 ticker 없음 | `—` |
| `targets_missing` | `목표 미설정` |
| `exit_leg=NONE` | `미도달` |
| FUND / VAL / BOTH | `도달(…)` |

신호강도·계단·근거는 Gap에 넣지 않음 (보유 리뷰만).

## 2. 테스트

`tests/test_gap_exit_status.py` + 기존 대시보드 표기 테스트 — **6 passed**.

## 3. 검증

| # | 결과 |
|---|------|
| 1 | Target 승인·⑥에 익절 표 없음 / 보유 리뷰 유지 |
| 2 | Gap 표 `익절상태` = board `exit_leg`/`targets_missing` 매핑; ETF 등 `—` |
| 3 | yaml 비면 kr_alpha 전부 `목표 미설정` (① 도달 의미·표시) |
| 4 | current/target/gap 수치 불변 |

라이브: 종합 포트 → 포트폴리오(티커) → 실제 vs 목표 Gap.
