# 경제 나침반 업그레이드 0~1단계 — 결과

> SPEC: [`ECONOMIC_COMPASS_PHASE_0_1_SPEC.md`](ECONOMIC_COMPASS_PHASE_0_1_SPEC.md)  
> ROADMAP: [`ECONOMIC_COMPASS_ROADMAP.md`](ECONOMIC_COMPASS_ROADMAP.md)  
> 원칙 준수: `score_*` 가중치·계수 미변경 · `src/alpha/` 미변경 · tilt만 축소 + 히스테리시스.

## 0단계 — tilt 축소 + 판정 로그

| 항목 | 내용 |
|------|------|
| `data/compass_rules.yaml` | `tilt_governance.taa_tilt_scale: 0.4` |
| `portfolio_builder.py` | raw tilt × scale 후 합산; `GroupAllocation.phase_tilt/regime_tilt` = **스케일 후** 값; `tilt_meta`에 raw/scaled 분리 |
| 하위호환 | `rules`/`tilt_governance` 없으면 scale=`1.0` (기존 테스트 기본 경로) |
| 로그 | `outputs/compass_judgment_log.jsonl` — `write_compass_judgment_log()` (`src/compass/judgment_log.py`) |
| 파이프라인 | `run_compass_pipeline` → compute(+output_dir) → build(+rules) → judgment log append |

**스키마 확인 키:** `date`, `run_id`, 4축 점수, `market_phase`/`computed_market_phase`, `computed_regime`/`applied_regime`, `override_active`, `compass_direction`, `taa_tilt_scale`, `raw_*_tilt`, `scaled_*_tilt`, `market_inputs`.

## 1단계 — 히스테리시스

| 항목 | 내용 |
|------|------|
| 설정 | `hysteresis.regime_confirm_runs: 2`, `phase_confirm_runs: 2` |
| 구현 | `src/compass/hysteresis.py` · `compute_compass(..., output_dir= / judgment_history=)` |
| 상태 소스 | `compass_judgment_log.jsonl` tail (별도 상태 파일 없음) |
| 순서 | computed → manual override → (override 없으면) 히스테리시스 → applied |

### CRISIS 비대칭 — 판단 근거

**진입 즉시 / 이탈만 지연**을 채택했습니다.

- 근거: VIX≥`crisis_vix` 또는 낙폭≤`crisis_kospi_drawdown`은 리스크 관리상 방어 비중 확대가 하루라도 늦어지면 손실 노출이 커짐(안전 방향).
- 반대로 CRISIS에서 일상 레짐으로의 복귀는 whipsaw가 잦을 수 있어 `confirm_runs`회 연속 non-CRISIS computed가 필요하다.
- `hysteresis_note` 예: `crisis_entry_immediate`, `crisis_exit_pending`, `crisis_exit_confirmed`, `regime_hold_pending`.

### 전환 횟수 시뮬레이션 (합성)

12일치 computed 시퀀스에 잡음(하루짜리 RISK_OFF 등)을 넣은 뒤:

| 방식 | 레짐 flip 횟수 (12일 합성) |
|------|----------------|
| 히스테리시스 없음 (computed 그대로) | 7 |
| confirm_runs=2 (+ CRISIS 비대칭) | 5 |

→ 감소 방향 확인. 월평균·실로그 누적은 4단계에서 재계측.

## 검증

| 항목 | 결과 |
|------|------|
| `tests/test_compass_tilt_hysteresis.py` | **6 passed** (scale 하위호환·축소·1일 스파이크 hold·CRISIS 즉시·이탈 지연·로그 스키마) |
| `tests/test_compass.py` 등 관련 | **통과** (기존 스위트, rules 미전달 → scale 1.0) |
| `run_compass_pipeline` (실데이터) | judgment log 1줄·`taa_tilt_scale=0.4`·kr_alpha `regime_tilt=-2.0`(raw -5 × 0.4) |
| `python -m src.main` | 선택 항목 — 원장 미실행(차단 아님) |

## 원장 검증 (2026-07-16) — **종결**

- 코드·yaml·산출물 3곳(kr_alpha raw −5 × 0.4 = scaled −2) 직접 대조 통과.
- 단위테스트 6건 로직 추적 — 형식적 통과 아님 확인.
- **캐비엇(비차단):** 실로그 1건이 `override_active=true`(수동 CAUTION)라 tilt 축소만 라이브 실증. 히스테리시스 자동판정 경로는 override 없는 날 로그 누적으로 관찰 예정(의도된 설계: override 시 히스테리시스 스킵).
- ROADMAP 0·1단계 → **완료** (1단계는 「라이브 관찰 지속」 주석).

## 다음

- 2단계(Turbulence Index) 스펙은 원장 작성 후 Cursor에 전달.
- 로그는 매매 게이트로 쓰지 않음(read-only 아카이브).
