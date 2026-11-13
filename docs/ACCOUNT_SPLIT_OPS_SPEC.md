# 계좌 이분 · 역발상 Soft 운영 (Review-only)

> **상태:** P0 운영 SoT · **일자:** 2026-11-12  
> **목적:** 정적/듀얼(앱 밖)과 Soft(일반)를 **합산 주문 없이** 닫고, 역발상은 **관찰·분할 게이트**로만 완성  
> **불변:** `pure_qvm` · `target` 사람만 · Soft+정적+듀얼 합산 집행 금지 · 주문 API 없음

---

## 1. 완성 정의

| 한다 | 안 한다 |
|------|---------|
| 계좌별 할 일 · 게이트 O/X/보류 (문서+UI) | 증권·연금 API · Executable 자동 |
| 가계% / 계좌% 지도 | Soft↔정적 비중 자동 이전 |
| 역발상 Soft 체인 Review | 저P→Soft 자동편입 · 바닥 매수 엔진 |

---

## 2. 계좌 이분 (가계=100)

코드: `OPS_STACK_BUDGET_PCT` · `STRATEGY_ACCOUNT` · `ACCOUNT_BUDGET_PCT`  
([`alpha_system/ui/services/strategy_candidates_board.py`](../alpha_system/ui/services/strategy_candidates_board.py))

| 계좌 | 가계 예산 | 전략 |
|------|-----------|------|
| **연금·ISA** | 85% | 정적 `compass_fit` 75 + 듀얼 GEM 10 |
| **일반** | 15% | 중기 Soft 12 + 단기 Soft 3 |

- **계좌%** = 해당 계좌 안 합 100 (집행 지도)  
- **가계%** = 가계 합 100 (참고)  
- Soft와 정적·듀얼을 **한 HTS/연금 주문에 넣지 않음**

### 오늘 할 일 (사람)

| 계좌 | 전략 | 주기 | 완료 조건 |
|------|------|------|-----------|
| 연금·ISA | 정적 | 연 1회·밴드 | 증권·연금 앱에서 비중만 복원 · Soft 종목과 한 주문 금지 |
| 연금·ISA | 듀얼 | 월 | 픽 1종만 · Soft와 합산 금지 |
| 일반 | 중기 Soft | 확인① 후 | Soft 통과 · 하루≤33% · 미집행=단기채 파킹 |
| 일반 | 단기 Soft | 위성 | 중기 전량과 섞지 않음 |

UI: 포트 › 유니버스 「오늘 계좌별 할 일」  
코드: [`account_ops_checklist.py`](../alpha_system/ui/services/account_ops_checklist.py)

---

## 3. 역발상 Soft 게이트 (일반 계좌만)

이론: [`research/strategies/contrarian-soft-gate-theory.md`](research/strategies/contrarian-soft-gate-theory.md)

**한 줄:** 유형 A(공포 타이밍 매수) 기각 · 유형 B(가치·해부·분할 Soft)만.  
**Fear:** 매수 **허가증이 아님** · `Fear ⇏ Buy` · hot이면 사이즈↓/보류 · 트리거로 쓰면 **FAIL→대기·파킹**.

전부 통과해야 **일반 Soft 매수 Review**. 하나라도 실패 → **대기·파킹** (매수 배지 없음).

1. **저P 티어 ≠ 매수** — 심층·정밀만 후보 · 관찰 풀 Soft 자동편입 없음  
2. **Soft∩논리가치** 또는 본질 2~3 · Soft 점수에 거시 서사 비가산  
3. **기업해부** PASS · HOLD≠보유 권고 · U(미확인)≠0  
4. **Fear·나침반** = 사이즈↓만 · 극단 공포≠매수 트리거 (`fear_as_buy_signal` → FAIL)  
5. **분할** — 하루≤33% · 원금메우기·전량바닥 금지  
6. **계좌=일반만** — 연금·ISA 예산으로 Soft를 채우지 않음  

보조지표(허가≠수익 · Fear 가용률 · 증빙 Soft · 사람위험):  
[`contrarian_soft_aux.py`](../alpha_system/ui/services/contrarian_soft_aux.py) · 이론 §6.

교차: [`BUY_SELL_MAP.md`](BUY_SELL_MAP.md) · [`KRX_LOW_PBR_OBSERVE.md`](KRX_LOW_PBR_OBSERVE.md) · [`MID_KOSPI_ENTRY_GATE_SPEC.md`](MID_KOSPI_ENTRY_GATE_SPEC.md) · [`FEAR_GREED_SOFT_SPEC.md`](FEAR_GREED_SOFT_SPEC.md) · `data/investment_stance.yaml`

---

## 4. 금지

- Soft + 정적 + 듀얼 **합산 주문**  
- `target_portfolio.csv` 자동 기입  
- Fear Soft·하드랜딩%·저P 명단 → QVM 가산  
- 연금 장부로 Soft 위성 집행  
