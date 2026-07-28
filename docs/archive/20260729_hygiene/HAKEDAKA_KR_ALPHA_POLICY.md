# 하케다카 ↔ kr_alpha 연동 정책 문서 (P8)

> 작성: Claude (독립 검증자) · 대상: 동준(운영자 판단) — **Cursor 구현 명세 아님**
> 목적: 하케다카-kr_alpha soft-preference 브릿지가 이미 구현·설정되어 있음을 문서화하고, `proposal_mode` 전환 시 지켜야 할 조건·금지사항·성공기준을 명시한다.
> 배경: 별도 코드 구현이 필요하다는 전제로 명세서 작성을 요청받았으나, 코드/설정/실측 CSV 대조 결과 **기능이 이미 존재**함을 확인. 이 문서는 "무엇을 만들 것인가"가 아니라 "이미 있는 스위치를 언제·어떻게 켤 것인가"를 다룬다.

---

## 1. 현황 문서화

### 1.1 구성요소 (신규 구현 불필요)

| 파일 | 역할 |
|---|---|
| `src/value_list/alpha_bridge.py` | universe 확장(`merge_hakedaka_into_universe`), 보너스 계산(`compute_hakedaka_alpha_bonus`), `proposal_mode` 분기(`proposal_sort_score`), 유동성 실패 시 보너스 무효화 |
| `src/value_list/overlap_diagnostics.py` | 50종 × kr_alpha 스코어 풀 교차 진단 → `outputs/hakedaka_overlap_diagnostics.csv` |
| `data/hakedaka_integration.yaml` | 전체 스위치·가드레일 (아래 1.2) |

### 1.2 현재 설정값 (`data/hakedaka_integration.yaml`)

```yaml
enabled: true
mode: soft_preference
proposal_mode: pure_qvm          # ← 핵심 스위치. pure_qvm = 보너스 미반영
hakedaka_tiebreaker_enabled: false
shadow_slot_candidate_enabled: true   # max_hakedaka_soft_slots: 1 (이론상)

hakedaka_role:
  forced_portfolio_slot: false
  qvm_replacement_allowed: false
  liquidity_bypass_for_proposal: false

portfolio_inclusion:
  hard_slot_enabled: false
  allow_if_liquidity_failed: false
  allow_if_qvm_failed: false
  allow_if_sector_cap_breached: false

review:
  require_human_approval: true
```

### 1.3 실측 상태 (`outputs/hakedaka_overlap_diagnostics.csv`, 49종 tier-H 기준)

| 지표 | 값 |
|---|---|
| `in_scored_pool=True` (kr_alpha 스코어 풀 진입) | **2종** — 동원산업(006040), 고려아연(010130) |
| 위 2종의 `fail_reason` | `pillar_threshold` (품질·밸류·모멘텀 최소 기준 미달), `qvm_grade=C` |
| `hakedaka_priority=True` | **0종** |
| 나머지 47종 탈락 사유 | `min_market_cap` / `liquidity_fail` / `market:시장 제외` (스코어 풀 진입 이전 단계에서 탈락) |

**결론**: `proposal_mode=pure_qvm`이므로 하케다카 정보는 현재 `total_score`에 전혀 반영되지 않는다(진단 태그로만 출력). 설령 `qvm_with_bonus`로 전환해도, 코드가 유동성 탈락 종목의 보너스를 무효화하므로(`alpha_bridge.py` 198-201행) 실질적으로 영향받을 수 있는 종목은 현재 **동원산업·고려아연 2종뿐**이며, 이마저도 `pillar_threshold`를 먼저 넘어야 한다.

---

## 2. `proposal_mode` 3단계 의미

| 값 | 효과 |
|---|---|
| `pure_qvm` (현재) | 하케다카 보너스 완전 미반영. 진단 전용. |
| `qvm_with_bonus` | 유동성 통과 종목에 한해 보너스(최대 16점, `bonus` 섹션)를 `total_score`에 가산 |
| `qvm_with_tiebreaker` | 동점·근접 구간에서만 순위 우대(`tie_breaker.max_rank_boost`), `hakedaka_tiebreaker_enabled: true`도 함께 필요 |

---

## 3. 전환 조건 (`pure_qvm` → `qvm_with_bonus` 또는 `qvm_with_tiebreaker`로 바꿀 경우)

이 전환은 **투자 정책 변경**이며 코드 수정이 아니다. `data/hakedaka_integration.yaml`의 `proposal_mode` 한 줄만 바뀐다. 전환 전 아래를 확인한다.

1. 운영자(동준) 명시적 결정 — `review.require_human_approval: true` 원칙과 동일하게, 이 값 변경도 동준 승인 없이 이루어지지 않는다.
2. 전환 직후 `python -m src.value_list.pipeline` (또는 해당 파이프라인 재실행) → `outputs/hakedaka_overlap_diagnostics.csv` 재생성
3. `in_proposal` / `hakedaka_priority` 컬럼이 실제로 몇 종 바뀌었는지 before/after 비교 (0종이어도 사실대로 기록)
4. `actual_buy_allowed`는 이 전환과 무관하게 여전히 `final_execution_decision.json` 재계산 결과에서만 나와야 함 — 전환으로 인해 자동매매가 열리지 않음을 확인
5. `scripts/verify_claude_review.py` 재실행 — `overall_pass` 유지 확인

---

## 4. 절대 금지

- `alpha_bridge.py` / `overlap_diagnostics.py` 로직 재구현 또는 우회 로직 신규 작성 금지 — 이미 있는 스위치만 사용
- `portfolio_inclusion.hard_slot_enabled`, `allow_if_liquidity_failed`, `allow_if_qvm_failed`, `hakedaka_role.liquidity_bypass_for_proposal`를 `true`로 바꾸는 것 — 이는 유동성/품질 하한 자체를 우회하는 것이므로 이번 정책 범위 밖 (별도의, 훨씬 더 신중한 논의 필요)
- `src/policy_cap.py`, `src/execution_scope.py`, `src/execution_guards.py`, `src/validation/bundle_consistency.py`, target_write/approval_bridge 관련 파일 — 이번 문서와 무관하게 항상 수정 금지
- `proposal_mode` 전환을 "버그 수정"이나 "성능 개선"으로 보고하지 말 것 — 정책 변경으로 명시

## 5. 성공 기준

- 판단 기준은 "더 많은 종목이 통과하는가"가 아니라 "`hakedaka_overlap_diagnostics.csv`의 `in_proposal`/`hakedaka_priority` 변화가 사실대로 추적되는가"이다.
- 전환 후에도 대부분(47/49종)은 여전히 유동성/시총 하한에서 탈락하는 것이 정상 결과다 — 이는 하케다카 리스트(저PBR 중소형 지주사 위주)와 kr_alpha 유동성 기준의 구조적 불일치이지, 연동 실패가 아니다.
- 실행(`actual_buy_allowed`, `target_write`)에는 어떤 경우에도 영향 없음 — 이 정책은 후보 스코어링 단계에만 영향.
