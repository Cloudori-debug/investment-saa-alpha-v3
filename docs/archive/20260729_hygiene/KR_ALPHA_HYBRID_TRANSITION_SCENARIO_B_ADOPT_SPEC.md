# 하이브리드 전환 — 시나리오 B 채택 반영 (실행 명세서)

> 선행: [`KR_ALPHA_DOMESTIC_BETA_CONCENTRATION_RESULT.md`](KR_ALPHA_DOMESTIC_BETA_CONCENTRATION_RESULT.md) §4 권고
> 원장 승인: 시나리오 B 채택 확정(2026-07-16).
> 원칙: **문서 개정만**. `target_portfolio.csv` 등 실제 파일 변경은 여전히 approval_bridge 승인 후.

## 1. `KR_ALPHA_HYBRID_TRANSITION_RESULT.md` §4 개정

기존 §4 배분표의 domestic_beta 행(`069500` 6.87%)을 **철회**하고 아래로 교체:

| 그룹 | ticker | 현행 target | 제안 target(B) | Δ |
|---|---|---:|---:|---:|
| kr_alpha | 005830 DB손해보험 | 3.81 | 3.50 | −0.31 |
| kr_alpha | 005440 현대GF홀딩스 | 1.15 | 2.50 | +1.35 |
| kr_alpha | 그 외 6+SK행 | 16.32 | 0 | −16.32 |
| income_alt | 161510 PLUS 고배당 | 3.59 | **11.79** | **+8.20** |
| income_alt | 279530 KODEX 고배당주(신규) | — | **7.08** | **+7.08** |
| domestic_beta | (신설 안 함) | — | — | — |

검산: (−0.31+1.35−16.32) + 8.20 + 7.08 = 0. kr_alpha 6.00% / income_alt 합 22.77%(기존 14.36%+8.51%p) — **domestic_beta 그룹은 이번 전환에서 생성하지 않음.**

## 2. 정책 충돌 재평가 (RESULT §2.4 갱신)

시나리오 B 채택으로 **`domestic_beta_note` 문구 개정은 더 이상 필요 없음** — 069500을 도입하지 않으므로 "국내주식 노출=kr_alpha가 대신한다"는 기존 정책 설계 전제가 깨지지 않음(단, kr_alpha 자체가 6%로 축소되므로 그 전제가 실질적으로 유효한지는 별개 논의 — 이번 문서 범위 밖).

남는 정책 충돌은 하나뿐:

| 문서 | 설정 | 제안 6%와 |
|---|---|---|
| `data/portfolio_policy.yaml` | `kr_alpha_min: 20` | 충돌(변경 필요) |
| `data/absolute_return_policy.yaml` | `kr_alpha_overlay_min_pct: 15.0` | 충돌(변경 필요) |

`domestic_beta_note` 개정 필요성은 **해당 없음으로 종결** — 다음 정책 스펙에서 이 항목은 제외하고 kr_alpha 하한 2건만 다룰 것.

## 3. 절대 금지

- 이 문서는 §1·§2 내용을 `KR_ALPHA_HYBRID_TRANSITION_RESULT.md`에 반영(개정)하는 것까지만. `target_portfolio.csv`/정책 yaml 실제 수정 금지.

## 4. 산출물

- `KR_ALPHA_HYBRID_TRANSITION_RESULT.md` §4·§2.4 개정판(같은 파일 갱신, 갱신 이력 남길 것).

## 5. 검증 체크리스트

1. §4 표가 B 숫자(161510 11.79 / 279530 7.08 / domestic_beta 없음)로 정확히 갱신됐는지.
2. §2.4에서 domestic_beta_note 개정 불필요 사실이 명시됐는지.
3. 실제 파일(target/정책) 미변경 확인.
