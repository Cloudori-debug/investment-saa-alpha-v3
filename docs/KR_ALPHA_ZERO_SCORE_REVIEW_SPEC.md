# kr_alpha 0점 3종목 — 원인 진단 및 교체후보 검토 (실행 명세서)

> ROADMAP: [`KR_ALPHA_STRATEGY_ROADMAP.md`](KR_ALPHA_STRATEGY_ROADMAP.md) §"결정된 다음 단계" 1.
> 원칙: 이 스펙은 **제안·진단까지만** — 실제 매도/매수 실행이나 `target_portfolio.csv` 변경은 범위 밖. 기존 승인 워크플로우(`approval_bridge`, 원장 승인)를 그대로 거쳐야 함.

## 0. 배경 — 원장이 직접 확인한 이상 신호

`outputs/alpha_signal_board.csv`에서 아래 3종목이 `total_score=0.0`·`review_action=REPLACE_CANDIDATE`로 잡혀 있음:

| 종목 | ROE | PER | PBR | fundamental_signal | valuation_signal |
|---|---|---|---|---|---|
| SNT홀딩스(036530) | 9.7% | 5.6 | 0.5 | quality 0 weak | valuation 0 stretched |
| 쿠쿠홀딩스(192400) | 11.0% | 5.5 | 0.6 | quality 0 weak | valuation 0 stretched |
| 현대그린푸드(453340) | 11.8% | 6.8 | 0.8 | quality 0 weak | valuation 0 stretched |

**의심되는 점**: PBR 0.5~0.8, PER 5.5~6.8은 전통적 가치투자 기준으로는 "저평가"에 가까운데 `valuation_signal`이 "stretched"(고평가)로 표시됨 — 상식과 반대 방향. `total_score`도 정확히 0.0(단순히 낮은 게 아니라 딱 0)이라, **진짜 최하위 평가인지, 아니면 결측치·계산 오류가 0으로 기본값 처리된 것인지 구분이 안 됨.**

## 1. 1단계 — 원인 진단 (실행 전 필수)

1. `total_score` 계산 로직(해당 함수 위치 확인 후)에서 이 3종목의 각 서브스코어(quality/valuation/momentum/flow 등) 원시값을 추적 — 정말 최하위 계산 결과인지, 아니면 특정 입력 데이터 결측(예: 특정 재무 필드 NaN → 0 fallback)으로 인한 것인지 확인.
2. `valuation_signal`이 "stretched"로 표시된 근거를 코드에서 찾아 — PBR 0.5~0.8을 "stretched"로 분류하는 게 의도된 로직(예: 업종 평균 대비 상대 비교, 또는 이익 감소 반영한 정당한 저PBR 등)인지, 버그인지 판별.
3. `risk_blocker`(SNT: `flow_distribution; position_overweight` / 쿠쿠·그린푸드: `screen_fail_or_low_score`)의 정확한 의미와, 특히 SNT의 `position_overweight`가 지난번 확인한 kr_alpha 전체 오버웨이트(31.91% vs 목표 22~24%)와 관련 있는지 확인.
4. **결과 보고만 하고, 이 단계에서 종목을 교체하지 않음.**

### 진단 결과에 따른 분기

- **계산 버그로 확인되면**: 버그 수정 스펙을 별도로 작성(이 스펙 범위 밖, 새 스펙 필요) — 점수가 재계산된 후 다시 판단.
- **정당한 최하위 평가로 확인되면**: 아래 2단계(교체후보 제안)로 진행.

## 2. 2단계 — 교체후보 제안 (진단에서 "정당" 결론 시에만)

1. 현재 투자유니버스(`outputs/alpha_shortlist.csv`, `outputs/alpha_candidates.csv` 등)에서 이 3종목을 대체할 후보를 스코어링 상위권에서 탐색.
2. 후보 선정 시 기존에 확립된 역할(role) 기준(quality_dividend/value_rerating 등, `EXIT_TARGET_SUGGESTION_RULE_SPEC.md` 참고) 및 지금 kr_alpha 보유종목들과 섹터 중복이 과도하지 않은지 확인.
3. 후보군 3~5개를 스코어·근거와 함께 표로 제시 — **매수 실행은 하지 않음.**
4. 교체 시 예상되는 거래비용(증권거래세 0.15~0.18% 등 `data/cost_assumptions.yaml` 참고)과 기존 보유분 매도 시 손익(단, `avg_price` 결측이라 정확한 손익 계산은 제한적임을 명시)을 함께 보고.

## 3. 절대 금지

- `data/target_portfolio.csv`, `data/user_target_portfolio.csv` 등 실제 목표 비중 파일을 이 스펙 범위에서 직접 수정하지 않음 — 제안만 하고, 실행은 기존 승인 워크플로우(`approval_bridge`)를 통해 원장이 별도로 승인.
- 진단 없이 바로 "점수가 낮으니 교체"로 넘어가지 않음 — §1 원인 진단이 선행돼야 함.
- 이 스펙 결과만으로 3~6종목 집중 전략으로 확대하지 않음(`KR_ALPHA_STRATEGY_ROADMAP.md`에 따라 집중 여부는 forward-return 데이터 누적 후 별도 판단).

## 4. 산출물

- `docs/KR_ALPHA_ZERO_SCORE_REVIEW_RESULT.md` — §1 진단 결과 + (해당 시) §2 후보 제안표.

## 5. 검증 체크리스트 (원장 확인용)

1. 3종목 각각 total_score=0.0의 원인이 명확히 설명됐는지(버그 vs 정당한 평가).
2. valuation_signal "stretched" 판정 근거가 납득되는지(PBR 0.5~0.8을 왜 고평가로 보는지).
3. 실제 파일 변경이 없었는지(git diff로 `data/target_portfolio.csv` 등 미변경 확인).
4. 교체후보 제안이 있다면 근거·거래비용이 함께 제시됐는지.
