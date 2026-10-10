# 경제 나침반 (Review-only)

> **상태:** Phase 1 MVP · **표시:** 사이드바「경제 나침반」(내부 키 `경제시그널`)  
> **일자:** 2026-10-10

## 역할

- **숲:** 글로벌 자산군(주식·국채·현금·금) 비중 Review  
- **나무:** 한국 주식은 포트폴리오 QVM·노른자 대기 — 나침반이 순위를 바꾸지 않음  

## 불변

- `target_portfolio.csv` · QVM 순위 · Core `score_m` 자동 변경 없음  
- 코스피/코스닥 · 중기/단기 장부 분리 유지  
- fund-screener와 합치지 않음  
- Executable(ETF·현금·채권)만 사람이 실행  

## 화면 순서

1. 지금 국면 (1–5 · 알파 봉투 개별주/단기채)  
2. 글로벌 슬리브 나침반 (4칸 권고 밴드)  
3. 지표 근거 + 슬리브 함의  
4. 과거 유사국면 빈도 표  
5. 지금 할 일 · 숲 방어  
6. 보유·제안 괴리 · 배당 힌트  

## 데이터

- 국면: FRED (기존 `economy_signal`)  
- 빈도 표: `alpha_system/economy_compass/data/stage_asset_frequency.json`  
  (문헌·역사 국면 버킷의 **사전계산** 승률·중앙값 · 온라인 전수 백테스트 아님)  
- 캐시: `data/local/economy_signal.json` (국면) · `data/local/economy_compass.json` (슬리브·빈도 스냅샷·proxy 메타)  
- Proxy 메타: SP500 / DGS10 / DFF / GOLDAMGBD228NLBM (빈도 캘리브레이션 출처 · 라이브 전수 pull 없음)

## 출처 메모 (해석·빈도)

- Bridgewater All Weather / 성장·인플레 박스  
- Morningstar Diversification Landscape (주식 스트레스 시 Treasury·금)  
- 금리·신용 긴축과 위험자산 (HY OAS, 실질금리, 커브)  
- AI·부채 사이클 경고는 **해설 문구**만 (자동매도 없음)
