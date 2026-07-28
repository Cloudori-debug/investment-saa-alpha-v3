# CECS 수동 채점 — 코어 후보 30종 (확정)

> 상태: **승인 완료** (2026-07-16)  
> 확정본: [`data/cecs_manual_scoring_candidates.csv`](../data/cecs_manual_scoring_candidates.csv)  
> 채점 템플릿: [`data/cecs_manual_scoring_template.csv`](../data/cecs_manual_scoring_template.csv)

---

## 승인 결정

| 항목 | 결정 |
|------|------|
| 규모 | **30종 유지** |
| KCC | **포함** — 보유 종목 CECS는 **청산 판단 재료** (편입·신규 매수 정당화 아님) |
| 금융 비중 | **인위 조정 없음** — P0~P5 `rank_score` 산출 결과 그대로 |

---

## 1. 선정 원칙 (적용됨)

| 우선순위 | 기준 |
|----------|------|
| P0 | 현재 보유 8종 전원 포함 |
| P1 | composite_score 상위 |
| P2 | score_sr (주주환원 서사) |
| P3 | 시총 상위 |
| P4 | 업종당 최대 4종 |
| P5 | stub 후순위 |

```
rank_score = 1000×is_held + 2×composite_score + 0.5×score_sr + min(market_cap/10조, 50)
```

> **2026-07-17 보완:** 위 P0·`is_held` 가산은 **CECS 채점 풀(30종) 구성**에만 해당.  
> **포트 선정(객관 6종)** 은 [`KR_ALPHA_SCREEN_OBJECTIVE_SIX_SPEC.md`](KR_ALPHA_SCREEN_OBJECTIVE_SIX_SPEC.md) 정책 **B** — 보유 참고 가능·강제 포함·순위 가산 금지.

---

## 2. 확정 shortlist (30종)

| 구분 | 종목 수 |
|------|--------:|
| 보유 (`is_held=true`) | 8 |
| 비보유 | 22 |
| **합계** | **30** |

**보유 8:** SNT홀딩스, 동원산업, DB손보, 오리온, 현대GF홀딩스, 코웨이, NICE평가정보, **KCC**  
**비보유 22:** SK하이닉스, 삼성전자, SK스퀘어, 신한지주, KB금융, … — 전체는 CSV `rank` 순.

### KCC (rank 8)

- `grade=Reject` 유지 — shortlist 포함은 **exit/청산 논지 입력** 목적
- CECS 채점 결과가 **편입·비중 확대 근거로 사용되지 않음** (템플릿 `notes`에 명시)

### 금융·지주 비중

P0~P5 자동 산출 결과 금융/지주 계열이 다수 — B안(주주환원 전반) gate_pass 풀 특성상 **의도적 쿼터 없음**.

---

## 3. 다음 단계

1. [`CECS_MANUAL_SCORING_TEMPLATE.md`](CECS_MANUAL_SCORING_TEMPLATE.md) 가이드에 따라 30종 DART 채점  
2. `rationale` 3건 필수 → `status=final`  
3. 팩터 CSV 병합 (`ticker`, 5팩터, `sector`, `cecs`) → 상관 리포트

---

*이전 제안 파일 `cecs_manual_scoring_candidates_proposed.csv`는 확정본 승격으로 삭제됨.*
