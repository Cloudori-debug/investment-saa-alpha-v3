# 익절 목표 근접도 — 결과

> SPEC: [`EXIT_TARGET_PROXIMITY_SPEC.md`](EXIT_TARGET_PROXIMITY_SPEC.md)  
> 원칙: **근접도 = 현재값/목표 비율(표시만).** 신호강도·계단 트림 계산과 분리. "확률" 금지어.

## 1. 변경

| 영역 | 내용 |
|------|------|
| 순수 함수 | [`take_profit_thesis.py`](../src/alpha/take_profit_thesis.py) — `compute_leg_proximity`, `format_proximity_*`; `TakeProfitAssessment`에 `fund/val_proximity_pct` |
| 보드 | [`alpha_signal_board.py`](../src/alpha/alpha_signal_board.py) — CSV 컬럼 `fund_proximity_pct`, `val_proximity_pct` |
| 보유 리뷰 | `근접도` 컬럼 (계단구간 옆). 미도달=`VAL 83.7% 근접` / 도달=`도달` / 미설정=`—` |
| Gap | `미도달 (VAL 83.7%)` 형태 접미사 |

## 2. 검증 (라이브 보드 재생성 후)

| # | 결과 |
|---|------|
| 1 | KT `VAL 83.7% 근접` · Gap `미도달 (VAL 83.7%)` |
| 2 | 동원 `FUND 81.5% 근접 / VAL 77.4% 근접` |
| 3 | SK하이닉스 근접도 `—` · Gap `목표 미설정` |
| 4 | 도달 시 근접도 칸=`도달` (계단구간은 기존 유지) |
| 5 | 금지어 정적 검사 + 테스트 **19 passed** |

신호강도는 미도달 시 여전히 `0.0`(의도). 근접도와 혼동하지 말 것.
