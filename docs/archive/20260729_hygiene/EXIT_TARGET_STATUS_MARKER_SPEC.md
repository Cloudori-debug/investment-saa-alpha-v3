# 익절 목표 미설정 — 즉시 인지 마커 추가 (경량)

> 배경: `ALPHA_SIGNAL_BOARD_DASHBOARD_EXPOSURE_RESULT.md`로 대시보드에 "익절 신호강도" 표는 노출됐지만, "목표 미설정" 여부가 다른 컬럼들 사이에 묻혀 있어 매번 포트를 확인할 때 바로 눈에 안 띔. 종목명 바로 옆(다른 값들보다 먼저)에 목표 설정 여부를 보여줘서 매번 인지되게 함.
> 원칙: **표시 순서·마커 추가만.** 계산 로직(`take_profit_thesis.py`, `exit_target_worksheet.py`) 변경 없음. `has_existing_target`/`targets_missing` 필드는 이미 계산되어 있음 — 이걸 더 잘 보이는 위치로 옮기고 아이콘화만 함.

## 1. 범위

### A. 대시보드 "익절 신호강도" 표 (`src/ui/alpha_panel.py` — `_render_take_profit_signals`)
컬럼 순서를 `ticker, name, 목표상태, 신호강도, 계단구간, exit_leg, 모멘텀오버라이드, trim_source_tag`로 변경 — **"목표상태" 컬럼을 name 바로 다음(맨 앞쪽)으로 이동**.
- `targets_missing=True` → `⚠️ 목표 미설정`
- `targets_missing=False` → `✅ 목표 설정됨`
(기존 "targets_missing" True/False 원본 컬럼은 제거하고 이 아이콘 컬럼으로 대체 — 중복 표시 방지)

### B. 워크시트 (`outputs/kr_alpha_exit_target_worksheet.csv` / `.md`, `src/alpha/exit_target_worksheet.py`)
`WORKSHEET_COLUMNS` 순서를 변경 — 현재는 `ticker, name, sector, role, current_weight_pct, target_weight_pct, roe, ..., has_existing_target, target_roe_min, ...` (목표 관련 컬럼이 맨 끝, name과 아주 멂).
변경 후: `ticker, name, 목표상태, sector, role, current_weight_pct, ...` — **"목표상태" 컬럼을 name 바로 다음으로 이동**.
- `has_existing_target=False` → `⚠️ 목표 미설정`
- `has_existing_target=True` → `✅ 목표 설정됨`
(기존 `has_existing_target` True/False 원본 컬럼 위치만 이동 + 표시값 아이콘화. `target_roe_min` 등 4개 빈 칸 컬럼은 그대로 맨 끝 유지 — 사람이 입력하는 자리이므로)

### C. (선택) 표 상단 요약 배너
두 위치 모두 표 바로 위에 한 줄 요약 추가: `"⚠️ N/7 종목 목표 미설정 — data/kr_alpha_exit_targets.yaml에서 직접 입력"` (N = targets_missing 카운트). 전부 설정되면 이 배너는 숨김.

## 2. 절대 금지
- `take_profit_thesis.py`/`exit_target_worksheet.py`의 계산·판정 로직 변경 금지 — 순수 표시 순서·아이콘화만
- `target_roe_min` 등 목표값 컬럼에 자동으로 값 채우기 금지 (기존 원칙 그대로)
- CSV 원본 컬럼명 자체를 바꾸는 건 무방하나(표시용 파생 컬럼 추가), 프로그램적으로 이 CSV를 읽는 다른 코드가 있다면 컬럼명 변경이 깨뜨리지 않는지 확인 필요 (worksheet CSV를 읽는 다른 소비자가 있는지 먼저 grep)

## 3. 검증 요청
1. 대시보드 "보유 리뷰" 탭에서 "목표상태" 컬럼이 name 바로 다음에 오는지, 7종 전부 현재 `kr_alpha_exit_targets.yaml`이 비어있으므로 `⚠️ 목표 미설정`으로 뜨는지
2. 워크시트 CSV를 열었을 때 두 번째 컬럼이 목표상태인지 (엑셀 등으로 열어도 스크롤 없이 바로 보이는지)
3. `target_roe_min` 등 실제 목표 입력용 4개 컬럼은 여전히 빈 칸으로 유지되는지 (이번 변경으로 값이 채워지면 안 됨)
4. 다른 코드가 `exit_target_worksheet.csv`의 컬럼 순서/`has_existing_target` 컬럼명에 의존하고 있는지 확인 — 있다면 호환 유지 방법 보고
