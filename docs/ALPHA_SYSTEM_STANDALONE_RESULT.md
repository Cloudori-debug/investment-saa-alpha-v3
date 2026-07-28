# 알파 단독 운용 시스템 — §7.1 RESULT

> SPEC: `docs/ALPHA_SYSTEM_STANDALONE_SPEC.md`  
> 완료일: 2026-07-16  
> 범위: **config 스키마 + 트랜치 상태머신(entry) + 하드 룰 3개만**. §7.2 이후 미착수.

## 판정

§7.1 완료. 확정값(30%·4×25%·하드 룰·`window_end`)은 스키마로 잠금. `[TODO]`는 null/빈 목록 + `ConfigTodoError`로 임의 채움 방지.

## 산출물

| 경로 | 역할 |
|------|------|
| `alpha_system/config/alpha_system.yaml` | 규칙·파라미터 (TODO null) |
| `alpha_system/schema.py` | Pydantic 스키마·잠금·`todo_fields()` |
| `alpha_system/loader.py` | YAML 로드 |
| `alpha_system/entry/` | 상태머신·하드 룰·`evaluate_entry` / `attempt_execute` |
| `alpha_system/{universe,scoring,sizing,exit,journal,report}/` | 스텁 (다음 모듈용) |
| `tests/test_alpha_system_entry.py` | 10 tests PASS |

## 하드 룰 동작

1. **소멸**: `as_of > window_end`(기본 2027-12-31) → 미집행 트랜치 `EXPIRED` + `REFLUX_TO_SAA`
2. **역방향 금지**: 트리거 미충족/`READY` 아님 상태에서 `attempt_execute` → `WARN_BLOCKED`
3. **논지 훼손 동결**: `thesis_damage_flag` 또는 config 이벤트 매칭 → `FROZEN` + reflux

## 고의로 안 한 것

- 스코어링 이식·팩터 상관 (§7.2)
- exit / journal / report / sizing
- `target_portfolio.csv` 연결·자동매매
- TODO 수치 임의 기입

## §7.1 점검 (2026-07-16)

### 1) 하드 룰 테스트 커버리지 — **포함 확인**

| 차단 경로 | 테스트 | 검증 |
|-----------|--------|------|
| 역방향 집행 → 차단 | `test_hard_rule_reverse_blocks_unmet_trigger` | T2 PENDING에서 `attempt_execute` → `WARN_BLOCKED` |
| window_end 경과 → EXPIRED | `test_hard_rule_sunset_expires_unexecuted` | as_of=2028-01-01 → 전 트랜치 `EXPIRED` + reflux×4 |
| 논지 훼손 → 미집행 전량 FROZEN | `test_hard_rule_thesis_damage_freezes` | `thesis_damage_flag=True` → 전량 `FROZEN` + FREEZE/reflux |

(정상 경로 `test_hard_rule_reverse_allows_ready_execute`, sunset 시 EXECUTED 유지 테스트도 별도 존재.)

### 2) T4 상태 정의 — **부분 구현 (스텁 아님, TODO 게이트)**

- `hybrid_rules is None`(기본 config) → T4는 **발화 불가**(detail에 `[TODO]`). 기본 경로에서는 PENDING 고정.
- `hybrid_rules`가 채워지면 **실로직**: 동일 평가 패스의 T2/T3 `trigger_met`을 참조.
  - `EXECUTED` prior는 `trigger_met=True`로 들어가므로 「이미 발동」으로 간주 → T4 미발화.
  - `mode=expire`면 기한 후에도 T4 미발화; 그 외 모드면 T2·T3 모두 unmet일 때 READY.
- **미구현**: T2/T3 「집행 완료」와 「트리거만 충족」을 구분하는 별도 플래그, 분할 집행 비율 구체값(TODO).

## 다음

**§7.2**: 스코어링 이식 + `eligibility`/`weight_input` 분리 + 팩터 상관 점검 리포트.

---

## §7.2 RESULT (2026-07-16)

### 판정

§7.2 완료. CECS·7축 계약·이중 출력·T2 중복 보고·상관 분석 코드·재채점 훅 반영.  
상관 리포트는 **데이터 없음 → status=SKIPPED** (가짜 수치 없음).

### 산출물

| 경로 | 역할 |
|------|------|
| `alpha_system/scoring/` | cecs / engine / correlation / overlap / rescore |
| `alpha_system/config/scoring.yaml` | 가중·상관 임계 (cutoff는 메인 yaml TODO) |
| `docs/ALPHA_SYSTEM_CECS_T2_OVERLAP_REPORT.md` | CECS↔T2 역할 중복 |
| `docs/ALPHA_SYSTEM_FACTOR_CORRELATION_REPORT.md` | 상관 리포트 (**SKIPPED**) |
| `tests/test_alpha_system_scoring.py` | T4·eligibility·상관 SKIP/OK |

### 이중 출력

- `eligibility`: `score_cutoff` 절대 비교 — 미설정 시 `None` + `ConfigTodoError` (상대순위 없음)
- `weight_input`: 편입 시 `total_score`, 미편입 시 `0`

### 상관 리포트 상태

`SKIPPED` — 종목 팩터 CSV 미제공. 요건은 리포트·`data_requirements()`에 명시.  
7팩터 단순화 판단은 **OK 리포트(high_pairs)** 확보 후로 보류.

### 다음

§7.3 `exit` 모듈 (임계값 TODO 유지).

---

## §7.3 RESULT (2026-07-16)

### 선행 — CECS-T2 high 중복 정리 (역할 근거, 상관 아님)

- `disclosure_status`, `independent_catalyst_flag` → CECS **가중 제외**, `T2.event_candidate_sources` 매핑
- CECS 잔여 가중 비례 재배분: execution 0.40 / pension 0.30 / purpose 0.30
- 상관·계약 축 **5팩터**: `score_q`, `score_v`, `score_sr`, `score_r`, `cecs`
- 문서: `docs/ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md`

### Exit 모듈

| 조건 | 동작 |
|------|------|
| 논지 훼손 (보유) | `LIQUIDATE` — entry `FROZEN`(미집행)과 구분 |
| 스코어 하락 | cutoff 있을 때만; action mode TODO 시 REDUCE placeholder |
| 목표 밸류 | `LIQUIDATE` (임계 TODO) |
| 윈도우 만료 | `PORTFOLIO_WIND_DOWN_REPORT` |

### 비대칭 하드 룰 (확정·동의)

- 진입 역방향 → **차단**
- 청산 조건 미충족 임의 탈출 → **경고만, 차단 안 함** (`WARN_DISCRETIONARY` + follow-through 저널)

### 테스트

`tests/test_alpha_system_{entry,scoring,exit}.py` — **27 passed**

### 다음

§7.4 journal/report 확장 (exit는 이미 `journal.record_action` 기록).

---

## 5팩터 계층 확인 (2026-07-16)

**누락 아님.** `execution/pension/purpose`는 CECS **내부** 하위지표.  
전체 스코어 = **Q/V/SR/R (종목 질)** + **CECS (촉매 확실성)** → 계약 축 5개.  
`docs/ALPHA_SYSTEM_FIVE_FACTOR_REWEIGHT.md`에 계층도 보강.

---

## §7.4 RESULT (2026-07-16)

### journal
- append-only (`append_record` / JSONL sink) — update/delete API 없음
- 필드: timestamp, action_kind, trigger_snapshot, score_snapshot, **rationale**, **discretionary_reason**
- `WARN_DISCRETIONARY` 시 `discretionary_reason` 필수 (`JournalValidationError`)

### report
- 단일 상태 리포트: 트랜치·스코어/eligibility·트리거·`days_to_window_end`
- 성과: 집행 단가(fills) 기록 + 벤치마크 비교는 TODO 훅만
- **재량 이탈 섹션**: WARN 누적 횟수·사유 목록 (규칙 재설계 신호)

### 테스트
`test_alpha_system_*.py` — **32 passed**

### 다음
§7.5 sizing (TODO 값 확정 후).

---

## Sizing TODO — 검토 대기 (2026-07-16)

운영자 확정 전. 제안 메모만 기록 (config 미기입).

| 항목 | 제안 범위 | 권고안 (미확정) | 비고 |
|------|-----------|-----------------|------|
| 종목 수 | 5~8 | **6** | 테마 상관↑ → 수↑해도 테마 리스크↓ 아님; 단독 운영·재채점 부담 |
| 초기 집행 상한 | 20~25% | **25%** | 6종 균등≈16.7% 대비 오버웨이트 여유; -60%→슬리브 -15% / 총자산 -4.5% |
| 평가액 상한 | 30~35% | **35%** | 초기와 분리 — 상승분 강제매도 회피, 초과 시 exit 감축 |

`total_score_blend` 0.70/0.30 → `FIVE_FACTOR_REWEIGHT.md` 추후 검토 목록 (상관 OK와 동시).

---

## §7.5 RESULT (2026-07-16)

### 확정·스키마 잠금

| 파라미터 | 값 |
|----------|-----|
| `target_names` | **6** |
| `initial_weight_cap` | **0.25** |
| `market_value_cap` | **0.35** |

### 배분 로직

- eligibility=True만, `weight_input` 비례 → iterative capping (`existing + incr ≤ 0.25`)
- 재배분 불가 잔액 → `unallocated_weight` + WARN (강제 채움 금지)
- 적격 < 6 → `shortfall_names` 리포트, 미달 종목 편입 금지
- **시장가 35%** 초과 감축 = **exit only** (`ExitReason.MARKET_VALUE_CAP`)
- 트랜치 누적: `existing_weights` 합산으로 cap 판정

### 테스트

필수 3케이스 포함 — **39 passed** (`test_alpha_system_*.py`)

### 모듈 개발 순서 (§7) — 완료

코딩 잔여가 아닌 투자 판단 TODO: T2 이벤트, T3 밴드, T4 규칙, score_cutoff, 청산 임계, 유니버스 경계, 벤치마크, 팩터 CSV→상관 리포트, blend 0.70/0.30 근거 검토.

