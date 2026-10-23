# L3 급락 방어 · 재진입 (Review-only)

> **일자:** 2026-10-23  
> **상태:** 채택 · 1A+2A  
> **불변:** `pure_qvm` · Core `score_m` 제외 · `target_portfolio.csv` 사람만 · 자동주문 없음 · 중기·단기 장부 분리  
> **연계:** [`TRAIL_EXIT_REVIEW_SPEC.md`](TRAIL_EXIT_REVIEW_SPEC.md) · [`crash_defense_signal.py`](../alpha_system/ui/services/crash_defense_signal.py)

---

## 한 줄

중기 보유가 **짧게 주저앉을 때** 일부 현금화 Review → **재진입가 사다리**로 다시 살 타이밍만 보여 준다.  
평단 −X% 기계 손절 없음 · 중기 전량은 L0/L1만.

---

## 트리거 (1-A)

| 코드 | 조건 | 배지 | trim |
|------|------|------|------|
| C1 | 5거래일 수익률 ≤ **−12%** | `급락줄이기` | 25% |
| C2 | 5일 ≤ **−18%** 또는 (C1 + L1 고점 DD ≥ T2=20%) | `급락환금` | 50% |
| C3 | 5일 ≤ **−25%** | `급락환금` + why에 전량 **검토** 힌트 | 50% (전량 강제 아님) |

입력: `data/prices.csv` 일봉 close (없으면 L3 미발화).  
L3 **단독으로 `exit_full` 금지**.

## 재진입 (2-A)

급락 발화 시 구간 저점 `crash_low` 기준:

| 단계 | 가격 | Review |
|------|------|--------|
| R1 | 저점 × 1.06 | 줄인 수량의 1/3 |
| R2 | 저점 × 1.12 또는 20일 고가 회복 | 추가 1/3 |
| R3 | 저점 × 1.18 | 잔여 (복원 상한 = trim 전 비중)

선택 로컬: `data/local/crash_defense_trim.json` — 사람이 방어 trim 저장 시 재진입 보드 고정.

## 병합 우선순위

1. S0 / L0·L1 `exit_full`  
2. L0·L1 `cash_half` vs L3 `급락환금` → 강한 쪽(동률이면 문구 병합)  
3. L0·L1 `trim` vs L3 `급락줄이기`  
4. `hold`

## 금지

- 평단 % 손절 트리거  
- score_m / QVM / target 자동 변경  
- 단기 장부에 L3로 중기 전량  
