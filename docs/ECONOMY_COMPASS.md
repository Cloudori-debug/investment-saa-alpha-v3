# 경제 나침반 (Review-only)

> **상태:** Phase 1 MVP · **표시:** 사이드바「경제 나침반」(내부 키 `경제시그널`)  
> **일자:** 2026-10-10

## 역할

- **숲:** 글로벌 자산군(주식·국채·현금·금) 비중 Review  
- **나무:** 한국 주식은 포트폴리오 QVM·노른자 대기 — 나침반이 순위를 바꾸지 않음  

## 불변

- `target_portfolio.csv` · QVM 순위 · Core `score_m` 자동 변경 없음  
- 코스피/코스닥 · 중기/단기 장부 분리 유지  
- fund-screener와 **엔진·DB 합치지 않음** (탭은 HTTP 읽기 전용만)  
- Executable(ETF·현금·채권)만 사람이 실행  
- 「비중 · Executable」: 슬리브당 ETF **2~3종** + 슬리브 내 비중·장부≈% · **경제노출=달러/글로벌**(국고·원화단기는 완충만) · 자동주문 없음  

## 화면 순서 (정보 트리)

상세: [`docs/UI_INFO_TREE.md`](UI_INFO_TREE.md)

- 상단 탭: **나침반** | **연기금 수급** (알파 내 브리핑 UI · 형제 `pension.db` 읽기 전용 우선 · 점수·target 불변)

**나침반 탭**

1. **결론 · 자산 움직임** — 알파 장부(개별주/단기채) + 숲 슬리브(늘림·줄임·유지 %) + 할 일  
   - 가계 전체 SAA 아님 · 자동주문·target 없음  
2. **왜 이렇게** — 국면·신용·실질금리·코스피 밸류 등 **핵심 지표만** (중복 카드·숲 수필 제거)  
2b. **바젤 관찰 · 전략 이행** — Soft 시간표 → 투자 방향 → 체크리스트  
    ([`BASEL_OBSERVATION_SPEC.md`](BASEL_OBSERVATION_SPEC.md) · target·자동주문 없음)  
3. **상품 후보** — Executable ETF 한 줄 목록 (결론과 분리)  
4. **상세 참고** — 정책 시간표·가설 상태·Basel Soft·**기관 원문 Soft**·사다리·지표·빈도 (접기)  
   - [`MACRO_POLICY_TIMELINE_SPEC.md`](MACRO_POLICY_TIMELINE_SPEC.md) · Basel≠붕괴 타이머 · 발표≠시행  
   - [`INSTITUTIONAL_REPORT_REVIEW_SPEC.md`](INSTITUTIONAL_REPORT_REVIEW_SPEC.md) — Fed·한은·IMF·BIS·SPF·ECOS · 사실≠전망 · 사람 메모만 · 점수 비가산  
   - **다시 계산** / **바젤 최신 확인**: BIS·연준 allowlist만 조회 → `data/local/basel_policy_live.json` · Soft t0·국내확인·점수 불변

**연기금 수급 탭** — 선정·형성·이탈 목록 + 알파 제안/보유 겹침 칩 · 형제 프로세스 필요  


## 국면 ≠ 자세권고

- **국면** = FRED `EconomySignal.stage` (캐시 불변 · 히어로 개별주/단기채 %)  
- **자세권고** = `build_bubble_stress_board` 오버레이 (`stress_overlay.py`)  
  - HY·커브·금리 등 위험 칸 ≥2 → `posture_stage = min(5, 국면+1)` (국면 없으면 4)  
  - 종목 자세·숲 방어·슬리브 밴드만 이 단계로 그림 · **target·QVM·주문 없음**  
  - 사모신용·AI 칸은 시계열 없으면 `데이터없음` (HY 대용·사람 Review)  
  - **유가·에너지** · **은행·비은행 신용** 칸 = 경로/메커니즘 안내 · `missing` · **자세 hot_count 제외** · 국면식 불변  
  - 유튜브·서사 = 가설 점검 문구만 · 자동 사실이 아님  

## 데이터

- 국면: FRED (기존 `economy_signal` — HY·실질·연준·BOJ·커브만 단계 산출)  
- 시장지표: `data/market_indicators.csv` (VIX·S&P·코스피…) — Fear&Greed Soft·평균회귀 Soft  
  - 「다시 계산」·확인①(하루 이상 정체 시)이 FRED와 **함께** 갱신 · KRX 실패해도 VIX/S&P는 외부로 전진  

- 신용 카나리아(국면 불변): FRED `BAMLH0A3HYC`(CCC OAS) · `BAMLC0A0CM`(IG OAS) → 점검판「CCC·저신용」「전염 패턴」(2023 국소 vs 2008 전염 가설)  
- TLT/LQD/HYG ETF 시세는 미수집(허용 소스 밖) · 스프레드로 대용  

- 빈도 표: `alpha_system/economy_compass/data/stage_asset_frequency.json`  
  (**예시·비검증** 캘리브레이션 · UI에 배너 표시 · 실시계열 백테스트는 Phase 2+)  
- 캐시: `data/local/economy_signal.json` (국면) · `data/local/economy_compass.json` (슬리브·빈도 스냅샷·proxy 메타)  
- Proxy 메타: SP500 / DGS10 / DFF / GOLDAMGBD228NLBM (빈도 캘리브레이션 출처 · 라이브 전수 pull 없음)

## 출처 메모 (해석·빈도)

- Bridgewater All Weather / 성장·인플레 박스  
- Morningstar Diversification Landscape (주식 스트레스 시 Treasury·금)  
- 금리·신용 긴축과 위험자산 (HY OAS, 실질금리, 커브)  
- AI·부채·사모신용 가설은 **점검판 + 자세권고** (자동매도·target·Core 변경 없음 · 시황 피드 아님)  
- **평균회귀·역발상 Review** (`mean_reversion_review.py`): 실질금리·VIX Soft·고가대비 · 공포 때 비중 복원 Review · QVM·월 리밸·L3와 같은 축 · 바닥 타이밍 없음 · **빠른 반등≠공격 전환** (금리·물가 경로 Review)
- **Fear&Greed Soft** (`fear_greed_soft.py`): CNN 7항 중 가용만 Soft 합산 · **원본 지수 아님** · 자세만 · **극단 공포→매수 트리거 금지** · Soft 사이즈는 실질금리·신용과 함께 Review · QVM·target 불변 · [`FEAR_GREED_SOFT_SPEC.md`](FEAR_GREED_SOFT_SPEC.md) · 학습 [`research/strategies/youtube-2026-fear-vs-rate-path.md`](research/strategies/youtube-2026-fear-vs-rate-path.md)
- **S&P 200일 Soft** (`spx_200dma_soft.py`): 강환국 1723 정합 · **2027H2(7/1)~** 이탈 시 주식 축소 Review · 이전은 관측 · 밸류 전량매도·듀얼 덮어쓰기·target 없음
- **막스 Continuum Soft** (`marks_continuum.py`): Investing Continuum 관찰 · **운영 한도 C2** · C3~C6는 경고만 · 전량·공매도·target 없음 · [`MARKS_CONTINUUM_SOFT_SPEC.md`](MARKS_CONTINUUM_SOFT_SPEC.md)
- **코스피 밸류 밴드 Review** (`kospi_valuation_band.py` · `data/kospi_valuation_history.csv`): PBR %ile 75/25 · 국면식 불변 · 싸다 단정·자동매수 없음 · [`KOSPI_VALUATION_BAND_REVIEW_SPEC.md`](KOSPI_VALUATION_BAND_REVIEW_SPEC.md)  
- **중기 Soft 코스피 신규 게이트** (`mid_kospi_entry_gate.py`): 밸류×고점대비×외인3일 Soft · 낙폭≠저가매수 · 코스피만 · 정적/Executable/코스닥 분리 · target·점수 불변 · [`MID_KOSPI_ENTRY_GATE_SPEC.md`](MID_KOSPI_ENTRY_GATE_SPEC.md)  
- 정적「숲 리스크 힌트」= 배경 해설만
- **투자 포트폴리오 · 운영 본체** (`static_body_pick.py` · `compass_exec_lab.py` · `stage_history.py`): **운영 본체=`compass_fit`(나침반적합 정의)** · Lab 점수표(정적·나침반 고정·월말 스위칭·|ρ|)는 **참고·성적 1등≠본체 승격** · 구 청구서완충(`invoice_buffer`)은 후보 제거·적합에 흡수 · Soft 자세 제외 · 비중 합성·yaml/Executable overwrite·Soft 합산·target 없음

## 나침반 적합 포트 (숲 본체 성격)

> Executable 표 = **오늘 전술 봉투** · 적합 포트 = **국면을 틀려도 버는 느린 숲 본체**.  
> 상세·갭·레시피: [`docs/research/strategies/static-all-weather.md`](research/strategies/static-all-weather.md)

| 축 | 맞음 | 아님 |
|----|------|------|
| 역할 | 글로벌 4슬리브 숲 본체 | Soft 개별주·target·QVM 장부 |
| 언어 | equity / bonds / cash / gold | 섹터·레버·나스닥100 단독 |
| 경제노출 | 달러·글로벌 주력 · 원화는 완충만 | 국고·예금이 듀레이션·대기 주력 |
| 예측 | 4박스로 문 지키기 | stage마다 전량 교체 |
| 리듬 | 연·분기 본체 + 얇은 봉투 틸트 | Executable % 월 복사 |
| 신용·금리 | 현금·단기·금 완충 | 장기채만 헤지 |
| 지역 | 주식 미·유럽·일본 축 공유 | 미국 S&P만 |
| 척도 | 생존·탄약·상관 완충 | 호황 Lab CAGR 1등만 |

**운영:** 본체≠Executable · Soft 합산 금지 · 틸트=슬리브 밴드 소폭 · 중립 `_REF`(주식40·국채25·현금20·금15) 근처를 흡수 · 개량은 정적 본체 점검이지 Executable 승격이 아님.  
**`compass_fit` 채권 보완:** 국채25(미10y 주력·국고 완충) ↔ 현금25(달러단기 탄약) · 30y는 본체 제외·Executable 틸트 · 단기채≠국채 사다리 비율.

**설계 검증 (2026-11-08):** 숲·본체·밴드%=**전역최적 아님 · 제약최적** · stage/빈도 숫자는 **예시 Soft** · 은·구리는 금 슬리브와 합치지 않음 · 상세 성적표 [`research/strategies/static-all-weather.md`](research/strategies/static-all-weather.md) §11 · 듀얼 유로 근사 [`research/strategies/dual-momentum-gem.md`](research/strategies/dual-momentum-gem.md).
