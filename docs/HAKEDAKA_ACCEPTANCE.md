# 하케다카 · 제안 포트 수용 기준 (AC-HK)

> `proposal_mode: pure_qvm` 기본 — 하케다카가 **최종 제안 순위를 바꾸지 않음**.

| ID | 기준 |
|----|------|
| **AC-HK-01** | `liquidity_pass=false` 종목은 `alpha_portfolio_proposal.csv`에 포함 불가 |
| **AC-HK-02** | `hard_slot_enabled=false` — 하케다카 단독 조건으로 제안 편입 불가 |
| **AC-HK-03** | `hakedaka_overlap_diagnostics.csv` row 수 = 고유 ticker 하케다카 종목 수 |
| **AC-HK-04** | `hakedaka_priority_review.csv` — QVM≥B · liquidity · DART verified 만 |
| **AC-HK-05** | `shadow_slot_candidate` — 표시용, `target_portfolio.csv` 자동 변경 없음 |
| **AC-HK-06** | sector cap · single-name cap · kr_alpha cap은 항상 우선 |

## proposal_mode

| 모드 | 제안 포트 영향 |
|------|----------------|
| `pure_qvm` | 하케다카 보너스·tie-breaker **미반영** (기본) |
| `qvm_with_bonus` | 보너스 반영 |
| `qvm_with_tiebreaker` | 보너스 + tie-breaker (`hakedaka_tiebreaker_enabled: true` 필요) |

테스트: `tests/test_hakedaka_acceptance.py`
