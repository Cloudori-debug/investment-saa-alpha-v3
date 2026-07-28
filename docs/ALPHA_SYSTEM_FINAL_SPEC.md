# 알파 단독 시스템 — 최종 확정 스펙 (마감 패키지)

> 작성: 2026-07-16  
> config 권위: `alpha_system/config/alpha_system.yaml` v0.2  
> 테스트: `tests/test_alpha_system_*.py` **50 passed**

---

## 1. 확정 파라미터 요약

| 영역 | 확정값 |
|------|--------|
| 총자산 한도 | 30% |
| 트랜치 | T1~T4 각 25% |
| `window_end` | 2027-12-31 |
| `go_live_date` | 2026-07-16 |
| sizing | 6종 / 초기 25% / 평가액 35% |
| 유니버스 | B안 — KOSPI + `data/universe_filter.yaml`, 금융 전용 필터 없음 |
| 벤치마크 | `KOSPI` (단일 문자열) |
| 5팩터 합성 | `0.70×factor_score_total + 0.30×cecs` (검토 대기) |
| CECS 수동 채점 | 30종 확정 — [`data/cecs_manual_scoring_candidates.csv`](../data/cecs_manual_scoring_candidates.csv) |

---

## 2. 트리거 패키지 (확정)

### T1 — 시간

- 시스템 가동(`system_started`) 즉시 READY

### T2 — 시장 이벤트 (OR, 1건이면 발화)

| event_id | 정의 |
|----------|------|
| `commercial_code_enforcement_decrees` | 상법개정 **후속 시행령·시행규칙** 관보 게재 |
| `msci_dm_index_inclusion_confirmed` | MSCI **선진국지수 편입 확정** (워치리스트 등재만은 비발화) |
| `ifrs18_domestic_adoption_schedule_confirmed` | IFRS18 **국내 적용 일정 확정** 고시 |

**제외 (논지 배경만):** 바젤3 — `thesis_background.basel3_excluded_from_t2: true`

**`event_candidate_sources` (발화 아님):** `disclosure_status`, `independent_catalyst_flag`

### T3 — 가격 (시장 PBR 밴드)

- **발화:** KOSPI 시장 PBR이 직전 **10년** 분포 **하위 20%** 진입
- **데이터:** `pykrx_kospi_aggregate_or_manual_feed`
- **판정 주기:** `monthly` — 스냅샷 `kospi_pbr_in_bottom_band: bool`
- **OR 훅 (미활성):** `or_eligible_avg_value_score.enabled: false` — 이력 축적 후 검토

### T4 — 혼합 (상태머신)

| 단계 | 조건 | 집행 |
|------|------|------|
| 초기 50% | 가동 **12개월** 경과 & T2·T3 **모두 미발동** | T4 weight의 50% → `PARTIAL_EXECUTED` |
| 잔여 50% | 이후 **T2 또는 T3** 발화 | 후발 추종 집행 → `EXECUTED` |
| 소멸 | `window_end`까지 잔여 미발화 | 잔여 → SAA 환류 (`EXPIRED`) |

상태: `PENDING` → `READY` → `PARTIAL_EXECUTED` → `READY`(follow-on) → `EXECUTED`

---

## 3. 재채점 트리거 (T2와 분리)

종목 레벨 공시 — `scoring.rescore_triggers`:

- `value_up_program_disclosure`
- `treasury_share_cancellation_resolution`
- `dividend_articles_amendment`

---

## 4. 청산·편입 규칙 (확정분)

| 규칙 | 내용 |
|------|------|
| 편입 게이트 | `exit.entry_require_target_valuation: true` — 종목별 목표 밸류 **미기입 시 편입 차단** |
| 목표가 수정 | `fundamental_event` + rationale 필수 저널; **가격 변동 사유 → WARN만** |
| 스코어 청산 | `score_cutoff` 확정 시 `exit.score_below_cutoff_action` 자동 연동 (현행 로직 유지) |
| 평가액 캡 | `market_value_cap` 35% — exit 전용 감축 |

---

## 5. 스왑 관찰 모드

```yaml
swap_rule:
  mode: observe_only   # reserved: active
  score_gap_pct: 20.0
  consecutive_hits: 2
```

- 재채점 시 비보유 적격이 보유 최하위를 **20% 이상** 초과, **2회 연속** → 리포트 `SWAP_CANDIDATE` + 저널
- **액션 신호 없음** — 추후 `active` 활성화 판단용 데이터

---

## 6. 하드 룰 (불변)

1. `window_end` 이후 미집행 → EXPIRED / SAA 환류  
2. 역방향 집행 차단 (`reverse_execution_blocked`)  
3. 논지 훼손 → FROZEN + 환류 (미집행 트랜치)

---

## 7. 남은 TODO — 결정 시점 구분

### 가동 전 결정

| 항목 | config 경로 | 비고 |
|------|-------------|------|
| **score_cutoff** | `scoring.score_cutoff` | 절대 컷오프 — 상관 리포트·CECS 채점 후 |
| **청산 임계 연동** | `exit.thesis_damage_exit`, `exit.score_below_cutoff_action`, `exit.target_valuation_exit`, `exit.window_end_portfolio_action` | cutoff 확정과 함께 |
| **thesis_damage_event_ids** | `thesis_damage_event_ids` | 논지 훼손 이벤트 ID |
| **CECS 30종 채점** | `data/cecs_manual_scoring_template.csv` | DART 수동 입력 → 팩터 CSV |
| **팩터 CSV → 상관 OK** | — | 5팩터 + sector + fallback 필드 |

### 운용 중 결정

| 항목 | 비고 |
|------|------|
| **blend 0.70/0.30** | 상관 리포트 OK 후 근거 검토 |
| **T3 OR 활성화** | `or_eligible_avg_value_score.enabled` — 적격군 V스코어 이력 36개월+ |
| **스왑 활성화** | `swap_rule.mode: active` — observe_only 저널 축적 후 |
| **CECS 자동화** | `fetch_cecs_inputs` — 상관 리포트 이후 |
| **벤치마크 성과 연동** | KOSPI 대비 초과수익 계산 훅 |

---

## 8. 관련 문서

| 문서 | 내용 |
|------|------|
| [`ALPHA_SYSTEM_STANDALONE_SPEC.md`](ALPHA_SYSTEM_STANDALONE_SPEC.md) | 원본 요청서 |
| [`ALPHA_UNIVERSE_B_SECTOR_META_RESULT.md`](ALPHA_UNIVERSE_B_SECTOR_META_RESULT.md) | 유니버스 B안 |
| [`CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md`](CECS_MANUAL_SCORING_CANDIDATE_CRITERIA.md) | CECS 30종 |
| [`CECS_MANUAL_SCORING_TEMPLATE.md`](CECS_MANUAL_SCORING_TEMPLATE.md) | 채점 가이드 |
| [`ALPHA_CECS_PROCESS_OPTIONS.md`](ALPHA_CECS_PROCESS_OPTIONS.md) | CECS 자동/수동 |

---

## 9. 이벤트 ID 레퍼런스

### T2 (시장)

```
commercial_code_enforcement_decrees
msci_dm_index_inclusion_confirmed
ifrs18_domestic_adoption_schedule_confirmed
```

### rescore (종목)

```
value_up_program_disclosure
treasury_share_cancellation_resolution
dividend_articles_amendment
```

### 저널 action_kind (신규)

```
SWAP_CANDIDATE
TARGET_VALUATION_MODIFY
WARN_TARGET_VALUATION_MODIFY
```

---

*본 문서는 config v0.2 + 트리거·청산·스왑 마감 패키지의 단일 참조본입니다.*
