# YouTube — 공포 매수 vs 금리·물가 경로 — 연구 카드

> **상태:** active · **학습·Review만** (`investment_stance` 자동 변경 없음)  
> **프로그램 매핑:** 경제 나침반 · Fear Soft · Soft 사이즈↓ · 평균회귀 Soft  
> **갱신:** 2026-11-09  
> **출처:** [YouTube QG40SUfIML8](https://www.youtube.com/watch?v=QG40SUfIML8)

## 1. 한 줄

공포·탐욕 지수로 “사서 반등”을 단정하지 말고, **남은 금리 인상 여지·물가 경로**로 반등의 지속 여부를 Review한다.

## 2. 우리 프로그램에서의 위치

- UI: 경제 나침반 태도 · Fear Soft · Soft 축소 Review
- 코드: `fear_greed_soft` · compass Soft · mid Soft cut · 평균회귀 Soft
- Soft/Review-only: **예** (매수·매도·target 자동 아님)
- target·QVM: **불변** · Soft 점수 비가산

## 3. 핵심 문헌·출처

| 문헌 | 연도 | 링크 | 요지 (요약) |
|------|------|------|-------------|
| YouTube 분석 | (영상) | https://www.youtube.com/watch?v=QG40SUfIML8 | Fear&Greed≤25 39회 · 공포 매수≠우위 · 금리·물가 5국면 |
| (기존) Fear Soft | — | [fear-greed-soft.md](../indicators/fear-greed-soft.md) | 자세 참고 · CNN 원본 아님 · 바닥 타이밍 금지 |
| (기존) 고금리 저주 | 2026-11 | [parkhonggi-20261105-high-rate-curse.md](parkhonggi-20261105-high-rate-curse.md) | 고금리·물가 병목 · 추격 금지 |

## 4. 연구 결론 (학습용 · 영상 요지)

- **설정:** 미국 고점 이후 AI·반도체 조정 · 공포탐욕 지수가 급락(예: 46→18)해도 “공포의 사”만으로 우위가 생기지 않음.
- **표본:** 2011~당해 9월, 지수 ≤25 구간 **39회**. 바닥까지는 대체로 빠름(한 달 반 이내 다수).
- **공포 시작일 매수:** 1년 후 상승 ~76% vs **아무 날 매수 ~86%** → 공포 타이밍이 평소보다 낫지 않음.
- **핵심 변수:** 반등 속도가 아니라 **반등이 얼마나 가는지** · 이를 가른 것은 **앞으로 금리가 더 오를 수 있는지**(현 금리 수준 자체보다 경로).
- **5국면 (영상 분류):**
  1. 금리≈0 · 물가 조용 → 대개 한 달 내 회복
  2. 인상 중 · 물가 조용 → 수개월(예: 2018)
  3. 인상 말기 · 물가 하향 → **결과 최상**(예: 2023)
  4. 인하 중 → 초반 MDD 크지만 1년 후는 대체로 회복(예: 2020·2025 관세)
  5. **고물가·지속 상승** → **유일 보통 손실** · 빠른 가짜 반등에 속기 쉬움(예: 2021→2022)
- **영상 현국면 가설:** 고물가 + 재인상 겹침에 가깝되, 2021(금리≪물가)과 2023(금리>물가) **사이** — 답은 공포 지수가 아니라 **물가 숫자**.

## 5. 우리 Soft로 옮긴 결론

### 나침반 (채택 · Review Soft)

- Fear Soft = **자세·관찰**만 · “극단 공포 → 매수” 트리거 금지
- Soft 신규·사이즈는 **금리·물가·실질금리·신용**과 함께 Review
- 평균회귀 Soft: 빠른 반등만으로 공격 전환 금지 (고물가·인상 여지 큰 국면의 가짜 반등)
- `ECONOMY_COMPASS` · `FEAR_GREED_SOFT_SPEC` · UI Fear/평균회귀 카피와 정합

### 듀얼 모멘텀 (Lab·해석만 · 시그널 불변)

- **한다:** 국면 Lab 해석 · “빠른 반등=주식 재진입” 금지 학습 · 절대모멘텀이 가짜 반등을 거르는 **부산물**로만 겹침 인정
- **하지 않는다:** Fear&Greed·CPI·영상 5국면을 상대/절대 규칙·월 시그널·Executable에 가산

### 공통 금지

- Fear Soft 합성 → target·주문·QVM 점수
- “공포니까 사서 메운다” 원금메우기 Soft
- CNN 원본 지수 필수화

## 6. 한계·주의

- 채널·표본·국면 라벨은 **영상 서술**이며 학술 복제 연구가 아님 · 미국 중심.
- “올해 9월 재인상·물가 4%” 등 **시점 서사**는 방송 시점 가정 — 나침반은 **현재 FRED·국내 지표**로 갱신.
- 한국 중기 Core·코스피/코스닥 장부 분리와 직접 1:1이 아님 · Soft Review 힌트만.
- Review-only · 투자 권유 아님.

## 7. 관련 카드·스펙

- [`indicators/fear-greed-soft.md`](../indicators/fear-greed-soft.md)
- [`FEAR_GREED_SOFT_SPEC.md`](../../FEAR_GREED_SOFT_SPEC.md)
- [`strategies/volatility-and-crash.md`](volatility-and-crash.md)
- [`strategies/parkhonggi-20261105-high-rate-curse.md`](parkhonggi-20261105-high-rate-curse.md)
- [`indicators/rates-real-yield.md`](../indicators/rates-real-yield.md)
- [`ECONOMY_COMPASS.md`](../../ECONOMY_COMPASS.md)
