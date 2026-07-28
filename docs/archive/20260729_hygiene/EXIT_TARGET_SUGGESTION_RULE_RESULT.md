# 익절 목표 제안값 (role+ROE 2요인) — 결과

> SPEC: [`EXIT_TARGET_SUGGESTION_RULE_SPEC.md`](EXIT_TARGET_SUGGESTION_RULE_SPEC.md)  
> 원칙: **재현 가능한 정책 초안** — yaml/`target_*` 자동 기입 없음. 배수·버퍼 미검증.

## 1. 변경

| 항목 | 내용 |
|------|------|
| 함수 | [`suggest_exit_targets`](../src/alpha/exit_target_worksheet.py) — 규칙 A(PBR 배수) · 규칙 B(role+ROE FUND) |
| 워크시트 | `suggested_roe_min`, `suggested_pbr_max` 참고 컬럼 / `target_*` **공란 유지** |
| 미적용 role | `제안 안 함` (예: `defensive_consumer`) — fallback 배수 없음 |
| MD | “재현 정책 초안·자동 복사 금지” 주석 |

## 2. ROE 버퍼 재현 메모

규칙 `round(roe + 2.5, 1)`을 그대로 적용. 수기 yaml과 소수 차이가 있을 수 있음(예: SPEC 표의 오리온/SNT/현대GF 수기 `12.5`/`12.0` vs 공식 `12.6`/`12.2`/`12.8`). **FUND 포함 여부·PBR 배수는 SPEC 표와 일치.**

## 3. 검증

| # | 결과 |
|---|------|
| 1 | 단위 테스트 8종: FUND omit/include·PBR·SK 보류 일치 |
| 2 | 워크시트에 suggested_* 존재, target_* 전부 공란, yaml 미변경 |
| 3 | 未知 role → `제안 안 함` (KeyError 없음) |

테스트: `tests/test_exit_target_worksheet.py` **4 passed**. 산출물 재생성: `outputs/kr_alpha_exit_target_worksheet.csv`.
