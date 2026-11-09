# 판단 지표 맵 — 프로그램 ↔ 연구

| 지표·게이트 | 쓰임 | 연구 카드 | 코드/데이터 |
|-------------|------|-----------|-------------|
| Q / V / SR / R (Core) | 중기 Soft 순위 | [strategies/qvm-soft.md](strategies/qvm-soft.md) | `alpha_scores` · `scoring.yaml` |
| `score_m` | Core **제외** · 단기만 | [strategies/short-momentum-satellite.md](strategies/short-momentum-satellite.md) | 차터 |
| 하케다카·품질 하한 | Soft 게이트 | [indicators/quality-gates.md](indicators/quality-gates.md) | hakedaka · min Q |
| Soft 모멘텀·ADV 컷 | 추격 매수 금지 | [indicators/soft-momentum-gates.md](indicators/soft-momentum-gates.md) | mid Soft cut |
| HY / CCC OAS · 커브 | 나침반 신용·자세 | [indicators/credit-spreads.md](indicators/credit-spreads.md) | FRED · stress overlay |
| VIX · 실현변동 | Fear Soft · vol Soft | [indicators/vix-vol-timing.md](indicators/vix-vol-timing.md) | `market_indicators` |
| S&P 200일선 | Soft 축소 Review (2027H2~) | [indicators/spx-200dma.md](indicators/spx-200dma.md) | `spx_200dma_soft` |
| Fear&Greed Soft | 자세 참고 · CNN 원본 아님 · 공포매수≠우위 | [indicators/fear-greed-soft.md](indicators/fear-greed-soft.md) · [strategies/youtube-2026-fear-vs-rate-path.md](strategies/youtube-2026-fear-vs-rate-path.md) | `fear_greed_soft` |
| 코스피 PBR 밴드 | 비쌈/쌈 Review · 단정 금지 | [indicators/kospi-valuation-band.md](indicators/kospi-valuation-band.md) | valuation band |
| 국채 10Y · 실질금리 | 국면·평균회귀 Review | [indicators/rates-real-yield.md](indicators/rates-real-yield.md) | korea_10y · FRED |
| 정성 게이트 | 제안 제외 Review | [indicators/qual-overlay-gates.md](indicators/qual-overlay-gates.md) | `qual_rank_overlay` |
