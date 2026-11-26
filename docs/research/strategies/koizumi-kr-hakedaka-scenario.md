# 한국판 하케다카 · 고이즈미 노믹스 벤치 시나리오 Lab

> **상태:** active · **Review-only** (`target`/QVM/자동주문 불변)  
> **프로그램 매핑:** Soft 50 · 자사주·행동주의 50 · 백테스트 Lab(시나리오 JSON)  
> **갱신:** 2026-11-25  
> **코드:** `alpha_system/shadow/koizumi_kr_hakedaka_scenario.py`  
> **산출:** `data/local/koizumi_kr_hakedaka_scenario.json`

## 1. 한 줄

일본 고이즈미 구간을 Soft에 **이식하지 않고**, 현재 Soft top · 행동주의 picks에 **강/중/약 국면 배율**만 얹어 50/50 가상 성과 밴드를 본다.

## 2. 벤치 앵커 (공개 요약)

| 앵커 | 요지 |
|------|------|
| 재임 TOPIX | 대략 **+15~20%** (취임~2006 중) |
| 회복 | **2003 봄** 이후 강세 · 저점 대비는 재임 합보다 큼 |
| 제도 | **2001** 자사주 매입 완화 · 지배구조·외국인 유입 동시 |
| Soft 카드 | [`parkhonggi-20261105-high-rate-curse.md`](parkhonggi-20261105-high-rate-curse.md) · 배당→M&A 가설 |

## 3. 시나리오 정의 (휴리스틱)

| id | 맵 | 코스피 | Soft | 행동주의 |
|----|-----|--------|------|----------|
| weak | 개혁 반쪽·역풍 | −5% | +2% | +8% |
| mid | 재임형 앵커 | +20% | +28% | +55% |
| strong | 강한 리레이트 | +80% | +95% | +140% |

- **50/50만기:** Soft 슬리브·행동주의 슬리브를 각 50%까지 채웠을 때  
- **실배치:** 지금 `of_mid_soft%` 가중(시드 seat면 행동주의≈12.5%·잔여 현금 0)  
MDD는 스트레스 **하한 밴드**.

## 4. Soft로 옮긴 결론

### 한다
1. 시나리오 JSON Review · Soft/행동주의 **이원** 유지  
2. mid에서 행동주의가 Soft보다 민감 → 승격·해부 우선순위만 점검  
3. weak에서도 Soft 추격 금지 · 하루≤33% 유지  

### 하지 않는다
- 일본 수익률 → 종목·target·QVM  
- Soft+행동주의 **합산 한 줄 주문**  
- 시나리오 % = Go-live·매수 신호  

## 5. 실행

```text
python -c "from pathlib import Path; from alpha_system.shadow.koizumi_kr_hakedaka_scenario import build_scenario_board, persist_board; print(persist_board(build_scenario_board(Path('.'))))"
```

## 6. 이원화 효용 검증 (가격)

코드: `alpha_system/shadow/dual_sleeve_utility_check.py`  
산출: `data/local/dual_sleeve_utility_check.json`

현재 Soft Lab top × 행동주의 picks(가격 있는 종목)로 Soft-only / 테마-only / 50/50 / 실배치 / (금지)합산EW를 비교.  
판정은 Review · 차터 이원 유지는 불변.

## 7. 한계

유추 Soft Lab · 하케다카 데이터 희소 · picks 공백 시 테마 축=현금. 과거≠미래.
