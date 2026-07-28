# 알파 익절 신호강도 — 대시보드 노출 명세서 (경량)

> 배경: `EXIT_TAKEPROFIT_THESIS_RESULT.md`로 1차(가시성) 구현 완료된 `tp_signal_strength`/`exit_leg`/`trim_source_tag` 등이 `outputs/alpha_signal_board.csv`에는 있지만, Streamlit 대시보드(`app.py` → `알파` 페이지)에는 아직 노출되지 않음 — 사람이 파일을 직접 열어야만 보임.
> 원칙: **신규 로직 없음.** 이미 계산된 값을 대시보드에 표로 보여주기만 함. execution/target 관련 코드 변경 없음.

## 0. 현재 상태 확인 (2026-07-15)

| 항목 | 상태 |
|---|---|
| 매수 후보 점수(quality/valuation/momentum/total_score) + `grade`(A~E) 계단형 등급 | **이미 대시보드에 노출됨** — `src/ui/alpha_panel.py` "QVM-SR 숏리스트" 탭, `penalty_engine.assign_grades` 기반 |
| 보유종목 리뷰 탭(`holdings_review.csv`) | 대시보드에 노출됨 — 단, `alpha_score`/`grade`/`review_action`만 있고 익절 관련 필드 없음 |
| 익절 신호강도(`tp_signal_strength`), 계단 구간(70-80/80-90/90+), `exit_leg`, `momentum_override_applied`, `trim_source_tag`, `tp_rationale`, `targets_missing` | **`alpha_signal_board.csv`에는 존재하지만 대시보드 어디에도 로드/렌더링 안 됨** ← 이번 SPEC 대상 |

## 1. 범위

### A. 데이터 소스
`outputs/alpha_signal_board.csv`를 `src/ui/alpha_panel.py`에서 `load_output_csv()`로 신규 로드 (기존 `holdings_review.csv` 로드 방식과 동일 패턴).

### B. 노출 위치
보유종목 리뷰 탭(기존 "보유 리뷰" 또는 동일 위치)에 아래 컬럼 추가 표시, 혹은 신규 서브탭 "익절 신호" 추가 (Cursor 판단에 맡김 — 기존 탭 구조 존중):

| 표시 컬럼 | 소스 | 표시 방식 |
|---|---|---|
| ticker, name | 공통 | — |
| tp_signal_strength | 그대로 | 숫자 (0-100) |
| 계단 구간 | `tp_signal_strength` → 밴드 매핑 | "70-80 (10%)" / "80-90 (20%)" / "90+ (30%)" / "70 미만 (—)" 식 텍스트 — `resolve_partial_frac_from_strength` 로직 재사용, 새 계산 아님 |
| exit_leg | 그대로 | FUND / VAL / BOTH / — |
| momentum_override_applied | 그대로 | 아이콘 또는 True/False |
| targets_missing | 그대로 | True면 "목표 미설정 — Hold" 배지 |
| trim_source_tag | 그대로 | TP-A / TP-B / TP-BOTH / targets_missing / — |
| tp_rationale | 그대로 | 툴팁 또는 expander |

### C. 표시 원칙 (기존 SPEC 계승)
- **"신호강도"/"스코어"만 사용. "확률"/"승률"/"성공확률"/"적중률" 단어 절대 금지** (`EXIT_TAKEPROFIT_THESIS_SPEC.md` §4 그대로 적용)
- `targets_missing=True`인 종목은 신호강도 숫자를 흐리게 표시하거나 "목표 미설정"으로 대체 — 0점과 혼동되지 않게
- 이 표는 **읽기 전용 리뷰** — 클릭으로 매매 실행되는 버튼/액션 추가 금지 (v1.0.2 execution authority 유지)

## 2. 절대 금지
- `alpha_signal_board.csv` 생성 로직(`src/alpha/alpha_signal_board.py`) 변경 금지 — 이미 검증 완료된 계산 로직, 이번 SPEC은 순수 표시(UI)만
- `take_profit_thesis.py`의 계산 로직 변경 금지
- 신규 매매 버튼/승인 액션 추가 금지 — 표시만

## 3. 검증 요청
1. 대시보드 "알파" 페이지에서 kr_alpha 7종 + Park 후보에 대해 `tp_signal_strength`/`exit_leg`/`trim_source_tag`가 실제 `alpha_signal_board.csv` 값과 일치하는지
2. 화면 어디에도 "확률"/"승률" 문구 없는지 (정적 검사)
3. `targets_missing=True` 종목(현재 7종 전부 — `kr_alpha_exit_targets.yaml`이 비어있으므로)이 화면에서 "목표 미설정"으로 명확히 구분되는지, 숫자 0/공백과 헷갈리지 않는지
4. 클릭 시 매매/target 변경이 발생하는 요소가 없는지 (읽기 전용 확인)
