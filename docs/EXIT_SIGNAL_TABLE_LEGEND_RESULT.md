# 익절 표 용어 범례 — 결과

> SPEC: [`EXIT_SIGNAL_TABLE_LEGEND_SPEC.md`](EXIT_SIGNAL_TABLE_LEGEND_SPEC.md)  
> 원칙: **안내 텍스트만** — 계산 로직 변경 없음

## 1. 변경

| 위치 | 내용 |
|------|------|
| 알파 → 보유 리뷰 | 「익절 신호강도」표 위 `st.caption`에 FUND/VAL/근접도/신호강도/exit_leg/trim_source_tag·단독설정 의미 |
| Gap 표 | `익절상태 = 목표 미설정 / 미도달(근접도%) / 도달(…) — 상세는 보유 리뷰 참고` |

## 2. 검증

| # | 결과 |
|---|------|
| 1 | 범례는 expander 없이 caption으로 즉시 노출 |
| 2 | Gap 한 줄 캡션 반영 |
| 3 | SPEC 원문 용어 키워드 정적 테스트 포함 |

테스트: `test_alpha_take_profit_dashboard` 범례 검사 포함.
