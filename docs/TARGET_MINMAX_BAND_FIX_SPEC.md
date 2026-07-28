# kr_alpha min/max 밴드 드리프트 — 수정 승인 명세서

> 근거: `docs/TARGET_MINMAX_BAND_MISMATCH_INVESTIGATION_RESULT.md` (원인 규명 완료, 독립 검증 완료)
> 운영자 결정: **8종목(071050 한국금융지주 포함) 구성 유지 + 밴드 1회 재동기화**
> draft(036530 SNT홀딩스) 복귀는 선택하지 않음 — 071050은 그대로 둘 것.
> 정책 캡 / dry-run / throttle / auto_trading 가드: **이번에도 미변경**

## 1. 승인된 작업 범위

투자 결과 문서의 제안 A + B + C를 이 순서로 구현한다. C(데이터 재동기화)는 A/B 코드 수정이 반영된 로직으로 실행해야 함 — 순서 뒤집지 말 것 (먼저 로직 고치고, 그 로직으로 현재 데이터를 재계산).

### A. `propose_target_changes()` 예산 스케일 시 밴드 동반 갱신

`src/alpha/target_bridge.py`의 `kr_alpha_budget` 스케일 블록(`row.target_weight = round(old * factor, 2)` 부분)에서:

- `min_weight`, `max_weight`도 **동일 factor로 스케일**하거나,
- tier 정보를 구할 수 있으면 `alpha_portfolio/src/target_matrix.py`의 `compute_bands(new_target, tier, cfg, kr_alpha_budget)`로 **재계산**.
- `src/compass/target_decomposer.py`의 `decompose_target_portfolio()`가 이미 target/min/max를 함께 스케일하는 정상 경로이므로, 그 로직과 동일한 원칙을 적용할 것 (동일 함수 재사용 가능하면 재사용, 아니면 동등한 로직으로 구현).

### B. 신규 add 후보 경로 — 기본 1.0/4.0 폐기

`resolve_add_candidate()` / `default_add_candidates()` (`src/alpha/target_bridge.py`):

- 후보에 min/max가 없을 때 무조건 `1.0/4.0`을 넣는 대신, 해당 종목의 `tier`/`role`에 맞춰 `compute_bands()`(또는 동등 satellite 캡 로직)로 산출.
- `default_add_candidates()`가 지금은 WATCH 상태도 통과시키는데, **WATCH/BLOCK_NEW_BUY 상태는 기본 add 후보에서 제외**하도록 필터 추가.

### C. 현재 live 데이터 1회 재동기화

운영자가 8종목(071050 포함) 유지를 확정했으므로:

1. A/B 반영된 로직으로 현재 `data/target_portfolio.csv` / `data/user_target_portfolio.csv`의 kr_alpha 8종목 min/max를 재계산.
2. 참고치: investigation 문서 기준 compass decompose가 산출한 071050 ≈ min 0.69 / max 4.58 등 — 이 계열의 "정상 경로로 재계산된 값"과 합치하는지 확인.
3. 반영은 반드시 `target_bridge`/`apply_proposed_target` 등 **기존 감사 로그가 남는 경로**로 수행 — CSV 직접 편집 금지.
4. `target_write_audit.jsonl`에 이번 재동기화가 "band_resync" 사유로 기록되도록 할 것 (사람 승인 흔적 유지).

## 2. 절대 금지 (변경 없음)

- `policy_cap_*`, BOK FSR 연동 로직.
- `execution_scope.py`, `core_deployment_throttle.py`, `execution_guards.py`의 게이트 임계값.
- `validators.py`의 min/max band 경고 로직 완화·삭제.
- 밴드를 "경고만 없애는" 방향으로 넓히는 것 — 반드시 A/B의 원천 공식(`compute_bands` 또는 decompose 스케일)에서 산출된 값만 사용.
- 071050 삭제 또는 036530으로의 임의 교체 — 이번 라운드는 8종목 유지가 확정 전제.

## 3. 검증 요청

1. A/B 코드 변경에 대한 단위 테스트 추가 (`propose_target_changes`가 budget 스케일 시 min/max도 스케일되는지, `resolve_add_candidate`가 WATCH 후보를 걸러내는지).
2. C 적용 후 `validate_inputs()` 재실행 — 6건 `target outside min/max band` 경고가 0건이 되는지 확인.
3. `input_validation_gate` 재계산 결과 GREEN 여부 보고.
4. `portfolio_gate`/`data_gate`는 policy_cap 때문에 YELLOW로 남을 수 있음 — 이건 실패가 아니라 예상된 결과이므로, 별도로 "왜 아직 YELLOW인가"를 policy_cap_active 사유로 명확히 구분해서 보고할 것.
5. 재동기화 전/후 `target_portfolio.csv` diff를 보고에 포함.
