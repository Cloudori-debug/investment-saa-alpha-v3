# kr_alpha 목표비중 min/max 밴드 불일치 조사 명세서

> 작성: Claude(검증자) · 대상: Cursor · 배경: `docs/ALPHA_GATE_DATA_GAP_INVESTIGATION_RESULT.md` 후속
> 정책 캡 / dry-run / throttle / auto_trading 가드: **이번에도 미변경**

## 1. 배경 (독립 검증으로 확인된 사실)

`src/validators.py`의 `validate_inputs()`가 `f"{ticker}: target outside min/max band"` 경고를 내면서 `input_validation_gate=YELLOW`를 유발하고 있음. 이게 `portfolio_gate` YELLOW의 두 원인(policy_cap과 별개) 중 하나.

`data/target_portfolio.csv`의 kr_alpha 8종목을 직접 대조한 결과, 6종목이 자기 자신의 min/max 범위를 벗어나 있음.

| 티커 | 종목명 | target_weight | min_weight | max_weight | 위반 |
|---|---|---|---|---|---|
| 030200 | KT | 4.07 | 5.36 | 16.05 | 하한 미달 |
| 021240 | 코웨이 | 4.07 | 5.36 | 16.05 | 하한 미달 |
| 005830 | DB손해보험 | 3.11 | 5.36 | 16.05 | 하한 미달 |
| 006040 | 동원산업 | 1.04 | 1.38 | 4.13 | 하한 미달 |
| 271560 | 오리온 | 1.04 | 1.38 | 4.13 | 하한 미달 |
| 071050 | 한국금융지주 | 5.56 | 1.00 | 4.00 | **상한 초과** |

(000660, 005440은 밴드 내 정상.)

min값이 030200/021240/005830 셋 다 5.36으로 동일, 006040/271560 둘 다 1.38로 동일 — **개별 종목별로 계산된 값이 아니라 역할(role)/티어 단위 고정값으로 보임.**

`alpha_portfolio` CECS 명세(`docs/05_CECS_TIER_WEIGHTING.md` 및 원본 `kospi_alpha_tier_weighting_spec.md`)는 **"7종목 기준"**으로 티어별 목표 비중을 설계했음. 그런데 현재 `target_portfolio.csv`의 kr_alpha는 **8종목**(071050 한국금융지주 role=`satellite` 포함). 종목 수가 설계 가정(7)보다 많아지면서 개별 비중이 더 얇게 나뉘었는데, min/max 밴드는 예전 기준(더 적은 종목 수 가정)에 맞춰진 채 갱신이 안 됐을 가능성이 있음.

**단, 이건 가설이지 확정된 원인이 아님 — 조사로 확인 필요.**

## 2. 조사 목표

1. `min_weight`/`max_weight`가 실제로 어디서, 어떤 로직으로 계산/기록되는지 추적 (`src/alpha/target_bridge.py`, `src/alpha/target_draft_bridge.py`, `src/alpha/target_portfolio_proposal.py`, `src/alpha/portfolio_selector.py`의 `_assign_role` 및 관련 티어 비중 로직 순서로 확인 권장 — 정확한 소스는 조사로 확정).
2. 071050(한국금융지주)이 언제/어떤 근거로 8번째 종목으로 추가됐는지 확인 (`decision_log.jsonl`, `target_write_audit` 이력 등).
3. 아래 중 하나로 분류:
   - **CONFIG_DRIFT_BUG**: min/max 밴드가 최신 종목 수(8)에 맞춰 재계산되지 않고 예전 값(6~7종목 기준)이 남아있는 경우 — 계산 로직을 종목 수/비중 배분에 맞게 갱신 필요.
   - **INTENTIONAL_TRANSITION**: 8종목 확장이 의도된 것이고, 지금은 과도기라 일시적으로 밴드를 벗어난 상태가 맞는 경우 — 이 경우 코드 수정 대신 밴드 자체를 8종목 기준으로 재설계할지 여부를 운영자 확인 필요.
4. 어느 쪽이든, **min/max 값을 그냥 넓혀서 경고를 없애는 임시방편은 금지**. 실제 배분 로직과 밴드 정의가 일치하도록 근본 원인을 먼저 특정할 것.

## 3. 절대 금지 사항

- `policy_cap_*`, BOK FSR 연동 로직 수정 금지.
- `execution_scope.py`, `core_deployment_throttle.py`, `execution_guards.py`의 게이트 조건/임계값 완화 금지.
- `validators.py`의 min/max band 경고 자체를 완화·삭제하는 방식으로 "해결"하는 것 금지 — 반드시 원인(밴드 정의 vs 실제 배분)을 먼저 규명.
- kr_alpha 종목 구성(8종목 유지 여부)을 임의로 되돌리는 것 금지 — 이건 운영자 판단 영역.

## 4. 보고 형식 (요청)

- 밴드값(min/max) 계산 로직의 소스 파일/함수 특정.
- 071050 추가 시점 및 근거.
- 6종목 각각 CONFIG_DRIFT_BUG / INTENTIONAL_TRANSITION 분류.
- CONFIG_DRIFT_BUG로 분류된 건에 한해 수정 방안 제안 (즉시 수정은 운영자 승인 후 진행 — 이번 라운드는 "원인 규명 + 방안 제안"까지만).
- `input_validation_gate` 재검증 결과 (수정 전/후 예상).

## 5. 우선순위 메모

`portfolio_gate`는 policy_cap(2026-09-24 재평가) 때문에 이 건을 고쳐도 당장 GREEN이 되지 않음. 급한 작업은 아니며, "정책 캡이 풀렸을 때 다음 병목이 되지 않도록" 미리 정리해두는 성격.
