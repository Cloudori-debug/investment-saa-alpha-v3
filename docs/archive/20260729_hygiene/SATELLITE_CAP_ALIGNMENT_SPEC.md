# 위성(Satellite) 단일 종목 상한 정렬 — 승인 명세서

> 근거: `docs/SATELLITE_WEIGHT_RULE_DUALITY_INVESTIGATION.md`
> 운영자 결정: **B(target_matrix 슬리브 5% ≈ 현재 kr_alpha 예산 기준 포트 ≈1.1%)를 운영 진실로 채택**
> CECS(A)는 삭제하지 않되, "별도 연구 트랙(비연결)"임을 문서화만 함
> 정책 캡 / dry-run / throttle / auto_trading 가드: **이번에도 미변경**

## 1. 결정 배경 (요약)

- CECS(`tier_allocator.py`)는 실제 target 산출 경로에 연결돼 있지 않은 별도 트랙 — 숫자만 빌려오면 "안 도는 시스템의 값을 도는 시스템에 이식"하는 셈.
- 실제 라이브 경로: `portfolio_selector.py`(QVM 제안, `max_proposed_weight_pct`) → `target_bridge.py`(승인·예산 스케일) → `target_matrix.py`(밴드, `satellite_cap.single_name_sleeve_pct: 5`).
- 앞으로 스크리닝이 계속 새 위성 후보를 내놓을 때, 그 후보를 **가장 먼저 처리하는 코드가 `portfolio_selector.py`**이므로, 여기 캡이 최종 밴드(B)와 안 맞으면 071050과 동일한 드리프트가 다음 종목에서 재발함.

## 2. 승인된 작업

### A. `portfolio_selector.py` 제안 캡을 B에 동적으로 정렬

- 현재: `max_single_pct = float(sel.get("max_proposed_weight_pct", 8.0))` — `data/alpha_scoring.yaml`의 고정값(포트폴리오 %, kr_alpha_budget 변화에 안 따라감).
- 변경: satellite 라벨(또는 tier) 후보에 대해서는, `alpha_portfolio/config/target_matrix.yaml`의 `satellite_cap.single_name_sleeve_pct`(현재 5)를 **현재 `kr_alpha_budget` 기준으로 환산**해서 사용 — 즉 `sleeve_to_portfolio(single_name_sleeve_pct, kr_alpha_budget)`를 호출해 동적으로 구함. `kr_alpha_budget`이 21.8%든 나중에 다른 값이든 자동으로 같이 움직여야 함.
- Core/Value 등 다른 role은 이번 범위 밖(다른 tier 캡 정렬은 별도 검토) — **이번엔 satellite만** 정렬.
- `alpha_scoring.yaml`의 `max_proposed_weight_pct: 8.0`은 하드코딩된 매직넘버로 두지 말고, target_matrix를 single source of truth로 삼아 값을 가져오거나, 최소한 값이 어긋나면 경고를 내도록 함.

### B. 071050(한국금융지주) 정렬

- 현재 5.56% → B 캡(현재 예산 기준 ≈1.09%, 정확한 값은 실행 시점 `kr_alpha_budget`으로 재계산)으로 축소.
- 반드시 감사 로그 남는 경로(`apply_proposed_target`, `approved_by="human"`)로 반영. **CSV 직접 편집 금지.**
- `write_reason`은 `"satellite_cap_alignment"` 등 이번 조치임을 알 수 있는 값으로.
- **중요**: 이건 target(타깃 비중) 변경일 뿐 실제 매매가 아님 — `Actual Buy Allowed=0`이 여전히 유효하므로 이번 조치로 실제 주문이 나가지 않음. 이 점을 결과 보고에 명시할 것.

### C. CECS(A) 트랙 — 문서화만

- `alpha_portfolio/docs/05_CECS_TIER_WEIGHTING.md` 및 관련 코드 상단에, "이 트랙은 live target 산출에 연결되지 않은 별도 연구/실험 트랙이며, 운영 진실은 target_matrix"라는 주석/문서 문구 추가.
- CECS 코드·테스트는 삭제하지 않음(추후 재검토 가능성 남겨둠).

## 3. 절대 금지

- `policy_cap_*`, `execution_scope.py`, `core_deployment_throttle.py`, `execution_guards.py` 변경 금지.
- `validators.py` band 경고 로직 완화 금지.
- 캡을 "경고 없애려고" 임의로 넓히는 것 금지 — 이번엔 B의 공식(sleeve % → 동적 포트 환산)으로만 산출.
- 071050 외 다른 종목의 role/tier 재분류 금지(범위 밖).

## 4. 검증 요청

1. `portfolio_selector.py` 단위 테스트: `kr_alpha_budget`을 다른 값(예: 15%, 25%)으로 바꿔가며 satellite 제안 캡이 함께 움직이는지 확인 — "스크리닝 후보가 바뀌어도/예산이 바뀌어도 캡이 같이 움직이는가"가 이번 정렬의 핵심 목적이므로 반드시 포함.
2. 071050 정렬 후 `validate_inputs()` — band 위반 0건 유지 확인.
3. `target_write_audit.jsonl`에 `satellite_cap_alignment` 사유로 기록됐는지 확인.
4. 정렬 전/후 `target_portfolio.csv` diff 보고.
5. CECS 문서에 "비연결 트랙" 문구가 추가됐는지 확인.
6. `input_validation_gate` / `portfolio_gate` / `data_gate` 최종 상태 재보고 (policy_cap 때문에 portfolio/data_gate는 YELLOW 유지 예상 — 실패 아님).
