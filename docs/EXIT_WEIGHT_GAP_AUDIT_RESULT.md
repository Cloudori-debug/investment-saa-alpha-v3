# 익절·테제·비중 로직 — 현황 점검 결과

> 근거 프롬프트: 익절 트리거 A/B · 테제 훼손 · 비중/히스테리시스/리밸런스  
> 일자: 2026-07-15  
> 범위: **조사만** — 본 RESULT는 코드를 바꾸지 않음

## 한 줄

퇴출은 “졌다/위험하다”(점수·게이트·수동 플래그) 쪽만 있고, **“이겼을 때 익절”**·**정책/테제 훼손 독립 편출**은 미구현. 운영 경로와 `alpha_portfolio` 퇴출 엔진이 이중이다.

## P0 확정 (원장 계획 승인 · 2026-07-15)

| 우선 | 항목 | 후속 문서 |
|------|------|-----------|
| **P0** | A-2 익절 A/B OR 부분익절 + B-5 테제/정책 훼손 편출 | [`EXIT_TAKEPROFIT_THESIS_SPEC.md`](EXIT_TAKEPROFIT_THESIS_SPEC.md) |
| **연기** | C 히스테리시스·상대 밴드 리밸 | 고정비중 vs 연속 매핑 결정과 **묶어서** 별도 명세 (아래 §C) |

## 항목별 요약

| ID | 판정 | 핵심 위치 |
|----|------|-----------|
| A-1 | 부분 구현 | `03_퇴출_규칙.md`, `alpha_exit_rules.yaml`, `exit_engine`, `holdings_review`, `alpha_signal_board` — 목표가 익절 없음 |
| A-2 | **미구현** | ROE/PBR 등은 스코어 입력·display만 |
| A-3/A-4 | **미구현** | A/B OR·경계 매트릭스 없음 → SPEC에 설계 |
| B-5 | **미구현** | CECS `policy_dependency` 페널티만, exit 경로 없음 |
| B-6 | 부분 구현 | H02/H07·보드 수동 hard flags; 경영권 분쟁 전용 없음 |
| C-7 | 부분 구현 | CECS mid×비례(live 비연결); ops=`target_matrix`+사람 승인 |
| C-8 | **미구현** | 티어 승격/강등 히스테리시스 없음; yaml 14일/2주 미반영 |
| C-9 | 부분 구현 | overweight %p·min/max 있음; 상대 25–30% 이탈 미정의 |

## 갭 목록 (리스크 큰 순)

1. **P0** 익절 A/B 전무 → SPEC  
2. **P0** 테제/정책 훼손 독립 경로 없음 → SPEC  
3. **P1** `exit_engine` vs `holdings_review` 이중 트랙 미통합  
4. **P1** yaml `soft_to_replace_days` / streak 미반영  
5. **P1** Tail/governance 자동화 공백  
6. **P2** 티어 히스테리시스 없음 → C 연기  
7. **P2** 상대 % 밴드 리밸 미정의 → C 연기  
8. **P2** CECS live 비연결 (오이식 주의)  
9. **P3** regime_overlay / S04·T04 disabled  

## C 연기 결정

- **고정비중 전환**을 검토하기 **전에** hysteresis + 상대 밴드 이탈을 같이 명세해야 whipsaw·거래비용이 설명 가능.
- 지금은 **별도 명세를 쓰지 않음**. 트리거: 「고정비중 vs CECS/QVM 연속 매핑」 운영 결정 직후 `WEIGHT_HYSTERESIS_REBALANCE_SPEC` (가칭) 작성.
- CECS 숫자를 live `target_portfolio`에 오이식하지 말 것 (`05_CECS_TIER_WEIGHTING.md`와 동일).

## 검증 피드백 반영 (2026-07-15)

원장 측 검증 후 SPEC에 보강(구조 변경 없음):

1. **데이터 유지 병목** — `EXIT_TAKEPROFIT_THESIS_SPEC` §3.1b: 사람이 YAML 유지·MVP=보유만·빈 목표=`Hold`/`targets_missing`.
2. **4트랙 정합** — §3.1c: TP는 `alpha_v2` shadow `trim_watch`(≥15%+수급 약화)를 **대체하지 않고 공존**. 출처 태그 분리. 엔진 병합 금지.
