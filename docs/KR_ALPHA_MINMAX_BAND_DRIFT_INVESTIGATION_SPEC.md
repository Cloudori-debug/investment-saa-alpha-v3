# kr_alpha min/max 밴드 vs 종목 수 불일치 조사 명세서

> 작성: Cursor · 검증자 권고 반영 · 대상: 원인 진단 우선 (수정은 분류 후)  
> 관련: `input_validation_gate=YELLOW` — `target outside min/max band` 경고  
> 우선순위: **중요하지만 비긴급** (정책 캡 해제 전 병목 정리)

## 1. 배경 (객관적 사실 — 예비 진단)

`validate_inputs` 경고는 “시세/재무 누락”이 아니라 **목표비중(`target_weight`)이 `min_weight`/`max_weight` 밴드를 벗어남**이다.

`scripts/diagnose_kr_alpha_minmax_bands.py` 로컬 스냅샷 (`data/target_portfolio.csv`, as_of 데이터 기준):

| 티커 | target | min | max | below_min | 비고 |
|------|--------|-----|-----|-----------|------|
| 071050 한국금융지주 | 5.56 | 1.0 | 4.0 | no | **max 초과** · draft에 없음 |
| 030200 | 4.07 | 5.36 | 16.05 | **yes** | min 클러스터 5.36 |
| 021240 | 4.07 | 5.36 | 16.05 | **yes** | 동일 |
| 005830 | 3.11 | 5.36 | 16.05 | **yes** | 동일 |
| 000660 | 2.02 | 0.0 | 10.71 | no | |
| 006040 | 1.04 | 1.38 | 4.13 | **yes** | min 클러스터 1.38 |
| 271560 | 1.04 | 1.38 | 4.13 | **yes** | 동일 |
| 005440 | 0.94 | 0.81 | 2.42 | no | |

- kr_alpha 행 **8종목**, 합계 target ≈ **21.85%**
- `alpha_portfolio/data/output/target_draft.csv` 도 8행이지만 **구성이 다름**: draft는 **036530** 포함, **071050 없음**. draft Core 목표는 7.0 / 7.0 / 5.36 … 이고 min=5.36·1.38 패턴이 draft와 동일 → **밴드 값은 draft(또는 그 직전 승인본)에서 왔으나, live target의 target_weight만 재배분·축소된 상태**로 보는 가설이 유력.
- 071050은 `role=satellite`, min/max=1.0/4.0 인데 target=5.56 → **상한 위반**. 승인·수동 편집·다른 브리지 경로 가능성.

검증자 가설: min이 role별 고정값처럼 보이며, **7종목 기준 밴드가 8종목 배분 후에도 재계산되지 않은 드리프트**.

## 2. 조사 목표

1. **왜 8번째 종목이 071050인가** (의도된 확장 vs 실수 vs 다른 파이프라인).
2. **min/max가 언제·어떤 공식으로 쓰였는지** (`target_matrix.yaml` 비율 vs 고정값 vs 승인 시 동결).
3. live `target_portfolio` vs `user_target` vs `target_draft` **diff 타임라인** (어느 단계에서 숫자만 바뀌고 밴드는 남았는지).
4. 각 경고 행을 **FIXABLE / EXPECTED** 로 분류.
5. FIXABLE만 수정안 제시. **즉시 min/max를 일괄 고치지 말 것** — 의도된 전환기를 되돌릴 위험.

## 3. 조사 단계

1. `data/target_portfolio.csv` · `user_target_portfolio.csv` · `alpha_portfolio/data/output/target_draft.csv` · (있으면) `outputs/proposals/*` · decision_log / target_write_audit 에서 **071050 유입 시점·소스** 추적.
2. `alpha_portfolio/src/target_matrix.py` + `config/target_matrix.yaml` 에서 min/max 산출식 확인 — draft의 5.36/1.38이 `target × ratio`인지, trim floor인지, 정규화 스케일인지.
3. 7→8 전환이 CECS `tier_weighting` / replace_pairs / 수동 승인 중 어디에 해당하는지 문서·커밋·감사 로그와 대조.
4. `src/validators.py` 가 min/max 위반을 어떻게 YELLOW로 올리는지 확인 (실행 완화 없음).
5. 분류표 작성 후, FIXABLE에 한해 **재계산 규칙(승인 시 밴드 재생성 vs draft 재승인)** 제안만 — 구현은 별도 승인.

## 4. 절대 금지 (운영·안전장치)

- `policy_cap_*`, BOK FSR, 만료일 로직 변경 금지.
- `execution_scope.py` / `derive_alpha_permissions` / dry-run 임계 완화 금지.
- `core_deployment_throttle.py`, `execution_guards.py` 변경 금지.
- “경고 없애려고” min/max를 임의로 target에 맞춰 낮추는 **일괄 패치 금지** (원인 미확인 시).
- 이번 작업으로 Actual Buy Allowed / data_gate를 GREEN으로 만드는 것을 성공 조건으로 두지 않음.  
  → 정책 캡(재평가 ~2026-09-24)이 풀리기 전 **다음 병목을 치워 두는** 성격.

## 5. 보고 형식

| 티커 | 현상 (below_min / above_max) | 유입·밴드 출처 | 분류 (FIXABLE/EXPECTED) | 원인 | 권고 조치 | 비고 |
|------|------------------------------|----------------|-------------------------|------|-----------|------|

추가로:

- 「7종목 설계 vs 8종목 실배분」결론 한 문단
- `input_validation_gate` 재현 조건
- 수정 시에도 **policy_cap 때문에 data_gate/매수는 당장 안 열릴 수 있음**을 명시

## 6. 재현 도구

```powershell
cd C:\Cursor\investment-saa-alpha
python scripts/diagnose_kr_alpha_minmax_bands.py
```

(스크립트는 read-only 진단. 수정 로직 없음.)
