# 경제 나침반 업그레이드 0~1단계 — 실행 명세서

> ROADMAP: [`ECONOMIC_COMPASS_ROADMAP.md`](ECONOMIC_COMPASS_ROADMAP.md)
> 원칙: **삭제·전면 재작성 아님.** 스코어링 함수(`score_growth` 등)와 `data/compass_rules.yaml`의 기존 임계값은 건드리지 않음. `src/alpha/`(kr_alpha), `take_profit_thesis.py` 미변경.

## 0. 조사 결과 (이번 세션에서 직접 읽은 코드 기준)

- 실제 tilt 반영 지점: `src/compass/portfolio_builder.py::build_portfolio_allocation()` 라인 76-88.
  ```python
  regime_tilts = get_regime_tilts(profiles, compass.applied_regime)
  phase_tilts = get_phase_tilts(profiles, compass.market_phase)
  ...
  raw_effective[group] = base + p_tilt + r_tilt   # base=SAA, p_tilt=국면, r_tilt=레짐
  ```
- tilt 값 출처: `data/saa_profiles.yaml` `taa_tilts`(레짐별) / `phase_tilts`(국면별). 예: `CRISIS` 레짐 `kr_alpha: -15`, `cash_short_bond: +15` — 최대 ±15%p 영향.
- 국면/레짐 산출: `src/compass/regime_engine.py::compute_compass()` — `_classify_risk_regime()`(라인 73-124), `classify_market_phase()`(`economic_phase.py` 347-359) 모두 그날의 시장지표만으로 즉시 판정, 이전 판정을 참조하지 않음(히스테리시스 없음).

## 1. 0단계 — tilt 축소 + 판정 로그

### 1.1 tilt 축소 (스케일 팩터)

**변경 파일**: `src/compass/portfolio_builder.py`, `data/compass_rules.yaml`

- `compass_rules.yaml`에 새 키 추가:
  ```yaml
  tilt_governance:
    taa_tilt_scale: 0.4   # 0단계 기본값 — 기존 대비 40%만 반영. 4단계 실측 후 조정.
  ```
- `build_portfolio_allocation()`에서 `phase_tilts`/`regime_tilts`를 `base`에 더하기 **전에** `taa_tilt_scale`을 곱한다:
  ```python
  tilt_scale = float(profiles.get("tilt_governance", {}).get("taa_tilt_scale", 1.0))
  ...
  p_tilt = phase_tilts.get(group, 0.0) * tilt_scale
  r_tilt = regime_tilts.get(group, 0.0) * tilt_scale
  ```
- `key_governance` 키가 없으면(하위호환) `tilt_scale=1.0`으로 기존 동작 유지 — 기존 테스트가 이 값을 명시적으로 안 준 경우 깨지지 않게.
- `GroupAllocation`의 `phase_tilt`/`regime_tilt` 필드는 **스케일 적용 후 값**을 기록(실제 반영치가 대시보드/로그에 나와야 함). **raw(스케일 전) tilt는 별도로 아래 1.2 로그에 기록** — 두 값이 헷갈리지 않게 필드명 구분(`raw_phase_tilt`/`raw_regime_tilt` vs 기존 `phase_tilt`/`regime_tilt`).
- 주의: `apply_bounds_iterative()`의 min/max 클램프 로직은 그대로 — tilt가 작아지면 클램프에 걸릴 일도 줄어드는 방향이라 안전한 축소.

### 1.2 판정 로그

**신규 파일**: `outputs/compass_judgment_log.jsonl` (append-only, 기존 `decision_log.jsonl` 패턴과 동일하게 1일 1줄 이상 가능)

각 파이프라인 실행마다 아래 필드를 기록(신규 함수 `src/compass/compass_pipeline.py`에 `write_compass_judgment_log()` 추가 또는 기존 파이프라인 훅 지점에 삽입):

```json
{
  "date": "2026-07-16",
  "run_id": "...",
  "growth_score": 0.12, "inflation_score": -0.05, "liquidity_score": 0.30, "risk_appetite_score": 0.18,
  "market_phase": "MARKET_RECOVERY", "phase_confidence": 0.55,
  "computed_regime": "YELLOW_STABLE", "applied_regime": "YELLOW_STABLE", "regime_confidence": 0.6,
  "override_active": false,
  "compass_direction": "N",
  "taa_tilt_scale": 0.4,
  "raw_phase_tilt": {"kr_alpha": 1, "cash_short_bond": -4, "...": "..."},
  "raw_regime_tilt": {"kr_alpha": 0, "...": "..."},
  "scaled_phase_tilt": {"kr_alpha": 0.4, "cash_short_bond": -1.6},
  "scaled_regime_tilt": {"kr_alpha": 0, "...": "..."},
  "market_inputs": {"vix": 17.2, "kospi_drawdown_pct": -2.1, "kospi_vs_ma200_pct": 3.4, "korea_10y": 3.1, "usdkrw": 1390, "oil_brent": 78, "foreign_flow_3d": "inflow"}
}
```

- `market_inputs`는 4단계(실측 검증) 때 재현·재계산에 필요하므로 원시값 그대로 남긴다.
- 이 로그는 **판정 기록용이지 매매 게이트가 아님** — 다른 어떤 실행 로직도 이 파일을 읽어 의사결정하지 않음(4단계 이전까지는 read-only 아카이브 성격).

### 1.3 검증 (0단계)

1. `python -m src.main` exit 0.
2. 기존 `tests/test_compass.py` 등 — 새 필드 추가로 실패하는 케이스 없는지(특히 `tilt_governance` 키 부재 시 기본값 1.0 하위호환 테스트 1건 추가 권장).
3. `outputs/compass_judgment_log.jsonl`에 최소 1줄 정상 기록 확인, 스키마 필드 전부 존재.
4. 대시보드/daily_report에 표시되는 실제 tilt 수치가 `taa_tilt_scale=0.4` 반영 후 값(축소된 값)인지 육안 확인.

## 2. 1단계 — 히스테리시스 (최소 지속기간)

### 2.1 개념

Bry-Boschan(1971) 방식 차용: 새로 계산된 국면/레짐이 즉시 적용되지 않고, **직전 N회 연속 파이프라인 실행에서 동일하게 계산돼야** "확정"되어 적용된다. 확정 전까지는 직전에 확정됐던 국면/레짐을 유지.

### 2.2 구현 방향

**변경 파일**: `src/compass/regime_engine.py`(`compute_compass()`), `data/compass_rules.yaml`

- `compass_rules.yaml`에 추가:
  ```yaml
  hysteresis:
    regime_confirm_runs: 2   # 연속 2회 동일해야 레짐 확정
    phase_confirm_runs: 2
  ```
- 상태 저장: 1.2에서 만든 `outputs/compass_judgment_log.jsonl`의 최근 N줄(`computed_regime`/`market_phase`)을 읽어 "직전 확정값 + 연속 미확정 후보값"을 판단하는 방식을 권장(별도 상태 파일을 새로 만들지 않고 기존 로그를 재사용 — 상태 파일 이중화로 인한 불일치 리스크 회피).
- `compute_compass()`가 `computed_regime`(그날 순수 계산치)과 `applied_regime`(확정 로직 통과 후 실제 적용치)을 이미 분리해서 반환하고 있음(`manual override`용으로 이미 존재하는 구조) — 이 구조에 **히스테리시스 확정 로직을 override 로직과 같은 위치(라인 193-213 부근)에 추가**하는 것을 권장. 즉:
  1. computed_regime 계산(기존 로직 그대로)
  2. manual override 체크(기존 로직 그대로)
  3. **신규**: override 없으면, 최근 로그에서 "확정 국면"과 비교 → 확정 국면과 다르면 "후보"로 기록만 하고 `applied_regime`은 기존 확정값 유지 → 후보가 `regime_confirm_runs`회 연속되면 그때 확정 전환.
- `market_phase`도 동일 패턴.
- CRISIS 레짐은 예외 처리 고려 필요(리스크 관리 관점): VIX≥30 같은 명백한 위기 신호까지 히스테리시스로 지연시키는 건 위험할 수 있음 — **CRISIS로의 진입은 즉시 적용(지연 없음), CRISIS에서의 이탈만 히스테리시스 적용**하는 비대칭 규칙을 권장(안전 방향 비대칭). 이 부분은 Cursor 구현 시 반드시 명시적으로 판단 근거를 RESULT 문서에 남길 것.

### 2.3 검증 (1단계)

1. `python -m src.main` exit 0, 기존 테스트 회귀 없음.
2. **시뮬레이션**: 0단계 로그가 쌓인 기간(또는 합성 테스트 데이터)에 대해 히스테리시스 적용 전/후 국면·레짐 전환 횟수를 비교 — 전환 횟수 감소 확인.
3. **단위 테스트 신규 추가**: 하루만 경계값을 넘었다가 다음날 원상복귀하는 합성 입력을 만들어, 히스테리시스 적용 시 `applied_regime`이 뒤집히지 않음을 확인.
4. CRISIS 비대칭 규칙: VIX 급등 시나리오에서 CRISIS 진입이 지연 없이 즉시 반영되는지 별도 테스트로 확인.

## 3. 완료 후 처리

- `docs/ECONOMIC_COMPASS_PHASE_0_1_RESULT.md` 작성(Cursor) → 이 문서 기준으로 검증 → `ECONOMIC_COMPASS_ROADMAP.md`의 상태표 갱신.
- 2단계(Turbulence Index) 스펙은 1단계 완료·검증 후 별도 작성.
