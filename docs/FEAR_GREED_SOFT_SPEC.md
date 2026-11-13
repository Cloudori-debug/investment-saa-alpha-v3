# Fear & Greed Soft (Review-only)

> **일자:** 2026-10-24  
> **불변:** QVM · `target_portfolio` · FRED 국면식 · 자세 `hot_count` 가산 없음  
> **코드:** `alpha_system/economy_compass/fear_greed_soft.py`

## 한 줄

CNN Fear & Greed **7항 체크리스트 + 가용 다리만 Soft 0–100**.  
**원본 CNN 지수가 아님.** 합산은 관찰·역발상/리밸 Review 힌트만.

## 다리

| Soft 키 | CNN 이름 | 데이터 |
|---------|----------|--------|
| momentum | Stock Price Momentum | 코스피 / 200MA (`market_indicators`) |
| strength | Stock Price Strength | 미수집 |
| breadth | Stock Price Breadth | 미수집 |
| put_call | Put and Call Options | 미수집 |
| volatility | Market Volatility | VIX (절대값 Soft · MA 미사용) |
| safe_haven | Safe Haven Demand | 미수집 |
| junk | Junk Bond Demand | HY OAS (`EconomySignal`) |

## UI

경제 나침반 「왜 이렇게」아래 + 더 참고「지표 · 단계」.

## Soft 리밸 A/B (예비)

코드: [`fear_soft_rebal_backtest.py`](../alpha_system/shadow/fear_soft_rebal_backtest.py)  
VIX Soft ∪ 코스피 고가대비 `hot` 날의 +20일 코스피 vs buy&hold.  
`market_indicators_history` **＜60행 → WAIT** (Phase2 게이트와 동일 정신).  
CLI: `scripts/run_l3_crash_backtest.py --fear-soft`

## Soft 해석 (나침반)

- 극단 공포 = **관찰·자세** · 매수 트리거 아님  
- Soft 사이즈·신규는 **실질금리·신용·물가 경로**와 함께 Review (공포 단독 우위 가정 금지)  
- System 1(패닉·대박 가용성) ≠ Soft 사이즈↑ · 원칙은 Fear Soft·배지 Review  
- **역발상 Soft:** Fear는 허가증이 아니라 **브레이크** · `Fear ⇏ Buy` · 트리거로 쓰면 게이트 FAIL→대기·파킹  
  ([`research/strategies/contrarian-soft-gate-theory.md`](research/strategies/contrarian-soft-gate-theory.md) · [`ACCOUNT_SPLIT_OPS_SPEC.md`](ACCOUNT_SPLIT_OPS_SPEC.md))  
- 학습: [`research/strategies/youtube-2026-fear-vs-rate-path.md`](research/strategies/youtube-2026-fear-vs-rate-path.md) · [`research/strategies/youtube-2026-kahneman-fast-slow.md`](research/strategies/youtube-2026-kahneman-fast-slow.md)  
- **듀얼 시그널에 미사용** (상대→절대 vs 달러단기만)

## 금지

- Soft 합산 → 자동주문 · target · score_m · 자세 상향  
- CNN API 스크랩을 확정 사실로 취급  
- WAIT 상태를 “검증 완료”로 표시  
- 듀얼 GEM 월 시그널·Executable에 Fear Soft 가산  


