# 5팩터 재구성 · CECS 가중 재배분 (§7.3 선행)

> 결정일: 2026-07-16  
> 근거: `ALPHA_SYSTEM_CECS_T2_OVERLAP_REPORT.md` high 중복 — **역할 분리(논리)**, 상관 기반 단순화 아님.  
> **계층 정정 노트 (2026-07-16):** “execution 0.40 / pension 0.30 / purpose 0.30”은 **CECS 내부 하위지표**이지, 전체 스코어가 3팩터로 줄었다는 뜻이 **아님**.

## 계층 (누락 아님 — 확인 완료)

```text
total_score = 0.70 × factor_score_total + 0.30 × cecs   ← 초기(검토) 식
                    │                         │
                    │                         └─ CECS(촉매 확실성) ← 하위 3가중 + policy 감점
                    │                              execution / pension / purpose
                    │                              (disclosure·independent → T2 후보만)
                    │
                    └─ factor_score_total = Q/V/SR/R 롤업  ← 종목 자체의 질
                         score_q 0.35 / score_v 0.30 / score_sr 0.25 / score_r 0.10
```

> **Ops A (2026-07-25):** 운영 채택 — `scoring.yaml` 의 `total_score_blend` 를 **factor 1.0 / cecs 0.0** 으로 변경.  
> CECS는 proposal 순위에 넣지 않고, 주간 정성 **T2·논지·목표가** 게이트만 필수로 둔다.  
> 위 0.70/0.30 식은 설계 이력·상관 검토용으로 유지.

| 층 | 역할 | 구성 |
|----|------|------|
| **5팩터 (상관·계약 축)** | 무엇을·얼마나 | `score_q`, `score_v`, `score_sr`, `score_r`, **`cecs`** |
| **CECS 내부** | 촉매 확실성만 | execution 0.40 / pension 0.30 / purpose 0.30 (+ policy 감점) |
| **T2 매핑 (비스코어)** | 언제 | `disclosure_status`, `independent_catalyst_flag` |

**판정:** 전자(퀄리티·밸류 계열이 CECS 밖에 별도 잔존). 후자(누락) **아님**.  
스코어는 “촉매 확실성만”이 아니라 **종목 질(Q/V/SR/R) 70% + CECS 30%** 블렌드.

## 결정

| 항목 | 조치 |
|------|------|
| `disclosure_status` | CECS **제외** → T2 `event_candidate_sources` |
| `independent_catalyst_flag` | CECS **제외** → T2 `event_candidate_sources` |
| 상관 축 | **5축**: `score_q`, `score_v`, `score_sr`, `score_r`, `cecs` |

## CECS 내부 가중 재배분 (하위지표만)

제외 전 CECS 가중합 1.0에서 disclosure 0.30 + independent 0.20 제거 → 잔여 0.50을 `×2` 스케일:

| 하위지표 | 재배분 가중 |
|----------|-------------|
| execution_continuity | **0.40** |
| pension_flow_score | **0.30** |
| investment_purpose_flag | **0.30** |

`policy_dependency_flag` 감점 가중(0.15) 변경 없음.

## 비대칭 하드 룰 (확정)

- **진입**: 트리거 미충족 집행 → **차단**
- **청산**: 조건 미충족 임의 청산 → **경고만**, 차단하지 않음 (+ §7.4 재량 이탈 리포트로 누적 감시)

## 추후 검토 목록 (상관 리포트 OK와 함께)

| 항목 | 현재 | 검토 시점 |
|------|------|-----------|
| `total_score_blend` **0.70 / 0.30** (factor_score_total : cecs) | `scoring.yaml` 초기값 — **확정 근거 미문서화** | 5팩터 상관 리포트(status=OK) 확보 후, 단순화 판단과 동시 검토 |
| 통계적 팩터 병합 (상관 high_pairs) | CSV 대기 | 동일 |
