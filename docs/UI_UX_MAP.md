# UI/UX 지도 — 알파 스크리너 (위성)

> 운영 여정 SoT · Review-only

## 일상

1. **확인①** — 정량·정성·수급·가계ETF Lab(하루1회)·나침반입력(FRED+VIX)·**전략 후보 스냅샷**  
2. **전략 운용** — Soft · 단기 · **정적 배분(달러축)** · **듀얼모멘텀(월 GEM)** + S&P200 Soft 관측  
3. **포트 · 유니버스(기본)** — 전략별 후보 지도 + 유니버스/박홍기 · **오늘 매매**는 Soft 집행  
4. **나침반** — 국면·자세 Review · Fear&Greed Soft · **S&P 200일 Soft(2027H2~)**  
5. **백테스트** — Soft Shadow 심화  

본체=`kr_listed_global`(미 국채·달러단기·금) · Soft=한국 위성 · 밸류만으로 전량매도·target 자동 없음.

## 포트

탭 순: **유니버스(기본)** | 오늘 매매  

유니버스 상단 = **추천 스택** 후보 (본체 `compass_fit` · 듀얼 선택위성 픽 · Soft · 단기). Lab 정적 전원 나열 아님.

## 전략 탭 갱신

| 전략 | 일상 | 탭 안 추가 |
|------|------|------------|
| 중기 Soft·단기 | 확인① | Soft 정량·후보 |
| 정적 배분 | 확인① Lab | 레시피 선택 · ETF Lab · 연 리밸 체크 |
| 듀얼모멘텀 | 확인① Lab | 시그널·가격 갱신 · 월말 전량 교체 Review |

자동주문·`target` 자동 **없음**. Soft=포트 집행 · 정적·듀얼=앱 밖. 본체 합산 집행 금지.

**데이터 막힘:** KRX·FRED·수급·정량 정체 등은 상단 운영여정 아래 **빨간/노란 알림**으로 표시 (`data_fetch_alerts`).

**시스템 점검:** 같은 위치 + 설정 › 데이터 상태에 점검표 (`system_health`). 막힘/주의면 Soft·나침반 숫자를 그대로 쓰지 말라는 문구. 펼치면 항목별 시각·상태.

SoT: [`UI_COPY.md`](UI_COPY.md) · [`V3_CHARTER.md`](V3_CHARTER.md)  
연구·근거: 사이드바 **더보기 › 연구·근거** · [`research/README.md`](research/README.md) · [`research/STRATEGY_MAP.md`](research/STRATEGY_MAP.md)
