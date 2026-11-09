# 전략 맵 — 프로그램 ↔ 연구

> Soft 위성 vs 본체(앱 밖) 구분 유지 · 합산 집행 금지

| 전략 (앱) | 역할 | 연구 카드 | 기존 스펙 |
|-----------|------|-----------|-----------|
| 중기 Soft (QVM) | 한국 주식 위성 · 포트 집행 | [strategies/qvm-soft.md](strategies/qvm-soft.md) | `FACTOR_WEIGHT_LITERATURE_AND_B_SPEC` · `ALPHA_BOOK_OPS_SPEC` |
| 단기 Soft | 모멘텀 위성 · Core `score_m` 불변 | [strategies/short-momentum-satellite.md](strategies/short-momentum-satellite.md) | `SHORT_BOOK_SPEC` · `MOMENTUM_REVIEW_ONLY_SPEC` |
| 정적 배분 (달러축) | 가계 본체 · 앱 밖 | [strategies/static-all-weather.md](strategies/static-all-weather.md) · 상관 Review | `household_static_alloc.yaml` · Lab · `corr_review` |
| 듀얼 모멘텀 (GEM) | 월 전량 1종 · 앱 밖 | [strategies/dual-momentum-gem.md](strategies/dual-momentum-gem.md) | 전략 › 듀얼 |
| 경제 나침반 국면·자세 | 태도 Review · 순위 불변 | [strategies/economy-compass-regime.md](strategies/economy-compass-regime.md) | `ECONOMY_COMPASS` |
| 변동성·위기 대응 | 사이즈↓ · 전량 전략교체 금지 · 공포매수≠우위 | [strategies/volatility-and-crash.md](strategies/volatility-and-crash.md) · [strategies/youtube-2026-fear-vs-rate-path.md](strategies/youtube-2026-fear-vs-rate-path.md) | L3 · Fear Soft · short vol |
| 계절성 (참고) | 단독 트리거 금지 | [strategies/seasonality-halloween.md](strategies/seasonality-halloween.md) | — |
| 기업해부(박홍기) | 오늘 2~3종 Review | (프로세스) `GIEOP_*` · [parkhonggi-20261105…](strategies/parkhonggi-20261105-high-rate-curse.md) | Soft 점수 비가산 · 시총 비정렬 |

## 최종 포트에서 쓰는 것

| 쓴다 (매매·보유) | 안 쓴다 (관찰만) |
|------------------|------------------|
| 중기 Soft 편입 · 실보유 · 팔 Review | 후보풀 · 정성게이트만 · Lab CAGR · 전략 비교표 |
| 할 일 사/유지/팔 · 하루≤33% | Soft+정적+듀얼 합산 주문 |
| Soft 공백 → 단기채 파킹 | target 자동기입 |
