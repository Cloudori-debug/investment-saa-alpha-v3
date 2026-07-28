# Target 승인 탭 익절표 되돌리기 + Gap 표 익절 참고 추가 (경량)

> 배경: `render_take_profit_signals(output_dir, widget_key="alpha_target_tab_take_profit")`가 `src/ui/alpha_panel.py` "Target 승인" 탭(target_draft expander 내부, line ~222)에 추가되어 있는 것을 확인. 이는 `ALPHA_SIGNAL_BOARD_DASHBOARD_EXPOSURE_SPEC.md`에서 지정한 범위(알파 → 보유 리뷰 탭)를 벗어난 배치 — 원장 확인 결과 되돌리기로 결정.
> 동시에 "종합 포트 → 포트폴리오(티커) → 실제 vs 목표 Gap" 표에 익절 참고 정보를 추가 (원장 선택: B안 + ①).
> 원칙: **표시만.** `take_profit_thesis.py`/`alpha_signal_board.py` 계산 로직 변경 없음. 신규 승인/매매 버튼 없음.

## 1. 범위

### A. Target 승인 탭 익절표 제거 (되돌리기)
- `src/ui/alpha_panel.py` line ~221-222: `render_take_profit_signals(output_dir, widget_key="alpha_target_tab_take_profit")` 호출 및 관련 주석(`# Display-only take-profit board next to draft tables (same as Step ⑥).`) 삭제.
- **알파 → 보유 리뷰 탭의 `_render_take_profit_signals` 호출은 그대로 유지** (건드리지 않음).
- `render_take_profit_signals` 함수 자체(재사용 가능하게 만든 public 버전)는 남겨도 무방 — 호출부만 제거.

### B. "실제 vs 목표 Gap" 표에 익절 참고 컬럼 추가
- 위치: `src/ui/portfolio_panel.py` `render_portfolio_page()` — `st.subheader("실제 vs 목표 Gap")` 이후 표시되는 `gap_df`/`_build_gap_table()` 결과.
- `outputs/alpha_signal_board.csv`에서 `ticker, exit_leg, targets_missing, tp_signal_strength, trim_source_tag`를 로드해 ticker 기준으로 Gap 표에 **읽기 전용 컬럼 "익절상태" 추가** (kr_alpha가 아닌 티커는 해당 데이터가 없으므로 "—").
- 표시 규칙 (① 실제 도달/권고 기준 — yaml 기입 여부(⚠️/✅)가 **아님**):
  - `targets_missing=True` → `"목표 미설정"`
  - `targets_missing=False`이고 `exit_leg="NONE"`(또는 매핑 없음) → `"미도달"`
  - `exit_leg="FUND"` → `"도달(FUND)"`
  - `exit_leg="VAL"` → `"도달(VAL)"`
  - `exit_leg="BOTH"` → `"도달(BOTH)"`
  - alpha_signal_board.csv에 해당 ticker 없음(비-kr_alpha) → `"—"`
- 신호강도(`tp_signal_strength`)는 이 표에서는 생략 — 상세 신호강도·계단구간·근거는 기존처럼 **알파 → 보유 리뷰 탭에서만** 확인 (중복 방지, Gap 표는 "도달 여부"만 참고용으로 간단히).
- `현재 %`/`목표 %`/`Gap` 등 기존 컬럼·정렬·계산 로직은 변경 없음. "익절상태"는 맨 끝 또는 gap 컬럼 바로 다음에 추가 (Cursor 판단).

## 2. 절대 금지
- `take_profit_thesis.py`, `alpha_signal_board.py`, Gap 계산 로직(`_build_gap_table`, `current_vs_target.csv` 생성) 변경 금지 — 순수 조회·병합·표시만
- Gap 표에 매매/승인 버튼 추가 금지 (읽기 전용 유지)
- "확률"/"승률" 등 금지 문구 재사용 금지 (기존 원칙 계승)
- 알파 → 보유 리뷰 탭의 기존 상세 익절 표는 변경 금지

## 3. 검증 요청
1. Target 승인 탭에서 익절 표가 더 이상 보이지 않는지, 보유 리뷰 탭에는 그대로 남아있는지
2. "실제 vs 목표 Gap" 표에서 kr_alpha 7종은 "익절상태"가 실제 `alpha_signal_board.csv`의 `exit_leg`/`targets_missing`과 일치하는지, 그 외 티커(ETF 등)는 "—"로 뜨는지
3. yaml이 비어있는 지금 상태에서 kr_alpha 7종 전부 "목표 미설정"으로 뜨는지 (①이 ②와 구분되어 표시되는지 재확인)
4. Gap 표의 기존 current/target/gap 값·정렬이 이번 변경으로 안 바뀌었는지
