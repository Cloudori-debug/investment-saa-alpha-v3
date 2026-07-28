# kr_alpha 목표가 워크시트 — 결과

> 명세: [`KR_ALPHA_EXIT_TARGET_WORKSHEET_SPEC.md`](KR_ALPHA_EXIT_TARGET_WORKSHEET_SPEC.md) (§0 3단계 구도 포함)  
> 일자: 2026-07-15  
> 원칙: **현재 관측값만** 모음. 목표값 칸 공란. `kr_alpha_exit_targets.yaml` 미기입.

## 0. §0 정합 (자동 vs 수동)

| 단계 | 역할 | 본 산출물과의 관계 |
|------|------|-------------------|
| ① 후보·스코어링 | 자동 (`factor_scoring` 등) | 워크시트가 `valuation_score`/`momentum_score` **읽기** |
| ② 익절 판정 엔진 | 자동 (`take_profit_thesis`) | yaml 비면 `targets_missing`/`Hold` — 본 SPEC 범위 밖 |
| ③ 목표치 | **수동** (`kr_alpha_exit_targets.yaml`) | 워크시트가 **쓰지 않음**; 사람이 채울 때 참고용 현재값만 제공 |
| 본 워크시트 | ③ 보조 | 목표 숫자 제안·자동 기입 **없음** |

## 1. 구현

| 항목 | 내용 |
|------|------|
| 모듈 | `src/alpha/exit_target_worksheet.py` — `build_exit_target_worksheet` / `write_exit_target_worksheet` |
| 출력 | `outputs/kr_alpha_exit_target_worksheet.csv` (+ `.md` 요약) |
| 파이프라인 | `post_decision_artifacts`에서 signal board 갱신 직후 호출 (게이트 무관·실패 시 soft) |
| 테스트 | `tests/test_exit_target_worksheet.py` |

출처(재사용만): `target_portfolio.csv`, `positions.csv`, `fundamentals.csv`, `hakedaka_fundamentals.csv`(payout), `alpha_scored_universe.csv`(스코어), `hakedaka_dart_events` / `treasury_events` / `dart_verification`(소각·취득 공시).

## 2. 검증

| # | 항목 | 결과 |
|---|------|------|
| 1 | kr_alpha 7종 포함·fundamentals 일치 | **원장 pass** — roe/pbr 소수점까지 대조 (예: 000660 36.12/14.68) |
| 2 | `target_*` 전부 빈 칸 | **원장 pass** — CSV·하드코딩 빈 문자열 |
| 3 | yaml 변경 없음 | **원장 pass** — sha256 / git diff 없음 |
| 4 | 신규 스크래핑 없음 | **원장 pass** — 로컬 CSV만 |

보유↔목표 갭(예: KT 0.45% vs 5.89%, 하이닉스 미보유 vs 2.95%)은 워크시트 버그가 아니라 dry-run / Actual Buy=0과 정합.

## 3. 운영

동준님이 CSV의 현재값을 보고 `data/kr_alpha_exit_targets.yaml`에 목표를 직접 기입. 워크시트는 yaml을 **읽기만** 하며 `has_existing_target`만 표시.
