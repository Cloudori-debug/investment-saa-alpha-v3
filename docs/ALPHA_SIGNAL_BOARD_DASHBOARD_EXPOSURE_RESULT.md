# 알파 익절 신호강도 — 대시보드 노출 결과

> 명세: [`ALPHA_SIGNAL_BOARD_DASHBOARD_EXPOSURE_SPEC.md`](ALPHA_SIGNAL_BOARD_DASHBOARD_EXPOSURE_SPEC.md)  
> 일자: 2026-07-15  
> 원칙: **표시만** — `alpha_signal_board` / `take_profit_thesis` 계산 로직 미변경

## 1. 구현

| 항목 | 내용 |
|------|------|
| UI | `src/ui/alpha_panel.py` — 알파 → **보유 리뷰** 하단에 「익절 신호강도 (읽기 전용)」 |
| 헬퍼 | `stair_band_label` / `prepare_take_profit_board_view` — `resolve_partial_frac_from_strength` 재사용 |
| 소스 | `outputs/alpha_signal_board.csv` (`load_output_csv`) |
| 테스트 | `tests/test_alpha_take_profit_dashboard.py` |

표시 컬럼: ticker, name, 신호강도, 계단구간, exit_leg, 모멘텀오버라이드, targets_missing, trim_source_tag + rationale에 tp_rationale.  
`targets_missing`이면 신호강도를 「목표 미설정」으로 표시(0과 구분).

## 2. 금지 준수

- signal board / take_profit 계산 미변경  
- 매매·승인 버튼 추가 없음  
- 「확률」「승률」 문구 없음 (테스트 assert)

## 3. 검증

단위: stair bands + targets_missing 표시 + 금지 단어.  
라이브: 대시보드 알파→보유 리뷰에서 CSV와 대조 (yaml 비면 전종목 「목표 미설정」).
