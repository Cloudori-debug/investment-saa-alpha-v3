# 주간 통합 정성 AI 요청서

- report_id: `WQR-20260724-225030`
- as_of: `2026-07-24`
- generated_at: `2026-07-24T22:50:30`
- input_snapshot_hash: `9af7bada868266da`

> 사실 조사 보조용입니다. 최종 점수·근거(rationale)는 출처 원문을 확인한 뒤 반드시 본인이 직접 작성하세요. AI 서술의 복사·붙여넣기는 채점 목적에 어긋납니다

## 작성 규칙

1. 섹션 헤더(`## A_CECS_SUMMARY` 등)와 필드 라벨을 변경하지 마세요.
2. 확인 불가한 항목은 추정하지 말고 근거에 `확인 불가; 검색 키워드: ...`를 적으세요.
3. 각 영역은 별도 승인됩니다. 한 섹션 실패가 다른 섹션을 자동 승인하지 않습니다.
4. `target_portfolio.csv` 변경 제안은 금지입니다. 목표가 YAML 제안만 허용합니다.
5. **숫자 칸 형식(파서 계약 — 반드시 준수)**
   - CECS `점수 제안(0-100):` → **숫자만**. 예: `65`
     금지: `65 (AI 초안)`, `65점`, `약 65`, 점수 칸에 `확인 불가`
     못 정하면 `_____`만 (업로드 시 잠정 50). `확인 불가`는 근거·출처에만.
   - 목표가 `pbr_max:` → **숫자만**. 예: `0.75`
     금지: `0.75배`, `0.7배 (2028년 목표)`, `1.4배 (대신증권…)`
   - 목표가 `target_price:` → **원 단위 숫자만** (쉼표·원·범위·주석 금지). 예: `48000`
     금지: `48,000원`, `200,000~250,000원`, `150000원 (한화…)`
   - `pbr_max`와 `target_price` 중 **최소 1개**는 숫자로 채우세요. 둘 다 `_____`면 업로드 실패.
   - 증권사명·범위·근거 설명은 `펀더멘털 사유`/`근거` 칸에만 쓰세요.
   - 출처 URL은 줄마다 단독으로 적어도 됩니다.

---

## A_CECS_SUMMARY

shortlist 30종 CECS 3축 요약. 종목 블록은 `## [TICKER] 이름` 형식을 유지하세요.
각 축의 `점수 제안(0-100):`은 숫자만(또는 `_____`). 괄호·주석·한글을 붙이지 마세요.

## [036530] SNT홀딩스
- 섹터: holding

### execution
- 점수 제안(0-100): 100
- 근거: 분기배당 4개 분기 연속(2025Q3~2026Q2, 기준일 각 분기말). 4/4.
- 출처:
  - https://stockanalysis.com/quote/krx/036530/dividend/
  - https://www.thinkpool.com/item/036530/disclosures/all/543008

### pension
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "SNT홀딩스 국민연금 지분율 2026". 확인 가능 최신 수치는 2021-01 4.19%(5% 미만).
- 출처:
  - 확인 불가; 검색 키워드: "SNT홀딩스 국민연금 대량보유상황보고서 2026"

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "SNT홀딩스 대량보유상황보고서 투자목적 2026". 최근 기관 투자목적 보고 미확인.
- 출처:
  - 확인 불가; 검색 키워드: "SNT홀딩스 기관투자자 5% 보고"

## [006040] 동원산업
- 섹터: consumer

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3 중간배당 550원, 2025Q4 자사주 취득결정, 2026Q1 결산배당 600원, 2026Q2 자사주 소각. 4/4.
- 출처:
  - https://www.newsis.com/view/NISX20250808_0003283975
  - https://kind.krx.co.kr/external/2025/11/18/000259/20251118000727/11332.htm

### pension
- 점수 제안(0-100): 85
- 근거: 국민연금 1.8%(2024말)→약 5.0%(2025)→5.01%(2026-04-09). 소각 규모 미미해 분모효과 배제, 순매수 확대.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680169

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(기준일 2026-04-09) 보유목적 단순투자.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680169

## [005830] DB손해보험
- 섹터: insurance

### execution
- 점수 제안(0-100): 50
- 근거: 2025Q4 자사주 소각, 2026Q1 결산배당·추가 소각. 2025Q3·2026Q2 이벤트 미확인. 2/4.
- 출처:
  - https://www.newsway.co.kr/news/view?ud=2025122219363639667
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=635462

### pension
- 점수 제안(0-100): 55
- 근거: 국민연금 7.21%(2025-01)→8.33%(2026-03). 소각 분모효과 가능·연속 순증 미확정으로 보수 채점.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=652394
  - https://www.ceoscoredaily.com/page/view/2026071410253328716

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(기준일 2026-03-30) 보유목적 단순투자.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=652394

## [271560] 오리온
- 섹터: consumer

### execution
- 점수 제안(0-100): 50
- 근거: 2026Q1 결산배당 3500원, 2026Q2 자사주 소각. 2025Q3·Q4 이벤트 미확인. 2/4.
- 출처:
  - https://www.mk.co.kr/news/business/11959739
  - https://www.yna.co.kr/view/AKR20260616099500030

### pension
- 점수 제안(0-100): 40
- 근거: 국민연금 10.53%(2024말)→9.95%→9.13%→8.12% 감소 후 9.14%(2026-02) 반등. 감소세 우세.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260401003292

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(반영기준일 2026-02-02) 보유목적 단순투자.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260401003292

## [005440] 현대지에프홀딩스
- 섹터: holding

### execution
- 점수 제안(0-100): 75
- 근거: 2025Q3 중간배당, 2026Q1 결산배당·자사주 매입, 2026Q2 매입 진행. 2025Q4 미확인. 3/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=663880
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=652401

### pension
- 점수 제안(0-100): 55
- 근거: 국민연금 2026-06-25 5.00% 신규 대량보유 진입. 이전 추세 미확인으로 보수 채점.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680168

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(기준일 2026-06-25) 보유목적 단순투자.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680168

## [021240] 코웨이
- 섹터: consumer

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3~Q4 자사주취득신탁 진행, 2026Q1 결산배당·소각, 2026Q2 분기배당. 4/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=565158
  - https://www.thinkpool.com/item/021240/disclosures/all/541929

### pension
- 점수 제안(0-100): 80
- 근거: 국민연금 6.67%(2025-03)→7.17%(2025말)→7.51%(2026-02-26). 연속 순매수.
- 출처:
  - https://news.einfomax.co.kr/news/articleView.html?idxno=4406201
  - https://goinsider.kr/stock/00170558

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(기준일 2026-02-26) 단순투자 유지.
- 출처:
  - https://goinsider.kr/stock/00170558

## [030190] NICE평가정보
- 섹터: financial_info

### execution
- 점수 제안(0-100): 50
- 근거: 2025Q4 자사주 소각, 2026Q1 결산배당 510원. 2025Q3·2026Q2 미확인. 2/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=601403
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=644220

### pension
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "NICE평가정보 국민연금 지분율 2025". 2026-04 5.00% 신규 진입만 확인, 연속 추세 미판정.
- 출처:
  - 확인 불가; 검색 키워드: "NICE평가정보 국민연금 대량보유상황보고서"

### purpose
- 점수 제안(0-100): 100
- 근거: 최신 대량보유보고(2026-07-10 피델리티) 보유목적 단순투자.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260710000217

## [002380] KCC
- 섹터: chemicals

### execution
- 점수 제안(0-100): 75
- 근거: 2025Q3 중간배당, 2026Q1 결산배당·소각, 2026Q2 이익소각. 2025Q4 계획만·실행 미확인. 3/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=684794
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=659223

### pension
- 점수 제안(0-100): 30
- 근거: 국민연금 보유주식수 감소(2026-04→05). 소각 분모효과와 별개로 절대주식수 감소 → 감소 추세.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=668488

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(2026-07-01) 보유목적 단순투자.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680226

## [000660] SK하이닉스
- 섹터: semiconductor

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3~2026Q2 매 분기 현금배당 확인. 4/4.
- 출처:
  - https://kr.investing.com/equities/sk-hynix-inc-dividends
  - https://www.datatooza.com/article/20260422173621488952ef385ee2_80

### pension
- 점수 제안(0-100): 85
- 근거: 국민연금 7.89%(2025Q4)→7.92%(2026Q1)→8.1%(2026Q2) 연속 상승.
- 출처:
  - https://news.tf.co.kr/read/economy/2343254.htm
  - https://www.yna.co.kr/view/AKR20260408157800008

### purpose
- 점수 제안(0-100): 100
- 근거: 최신 대량보유보고(2026-06-09 Capital Research) 보유목적 단순투자.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260609000049

## [005930] 삼성전자
- 섹터: semiconductor

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3~2026Q2 분기·결산배당 확인. 자사주 소각 프로그램 병행. 4/4.
- 출처:
  - https://www.yna.co.kr/view/AKR20260430046800003
  - https://siglab.kr/samsung-dividend-2026/

### pension
- 점수 제안(0-100): 70
- 근거: 국민연금 7.57%→7.77%→7.75%(보합)→7.9% 전반 우상향. 보수적으로 70.
- 출처:
  - https://www.yna.co.kr/view/AKR20260408157800008
  - https://www.newsis.com/view/NISX20260714_0003708893

### purpose
- 점수 제안(0-100): 30
- 근거: 최신 대량보유보고(2026-07-10 삼성물산 등) 보유목적 경영권 영향.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260710000678

## [402340] SK스퀘어
- 섹터: holding

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3~2026Q2 자사주 매입·소각 분기별 확인(공식 IR). 4/4.
- 출처:
  - https://www.sksquare.com/kor/ir/return.do

### pension
- 점수 제안(0-100): 90
- 근거: 국민연금 6.89%(2024말)→7.67%→8.48%~8.84%→8.80%대 연속 상승 방향.
- 출처:
  - https://www.newsis.com/view/NISX20260714_0003708893
  - https://activeholders.com/companies/402340

### purpose
- 점수 제안(0-100): 100
- 근거: 최신 대량보유보고(2026-06-08 노무라) 보유목적 단순투자.
- 출처:
  - https://activeholders.com/companies/402340

## [005935] 삼성전자우
- 섹터: semiconductor

### execution
- 점수 제안(0-100): 100
- 근거: 삼성전자 보통주와 동일 이사회 배당 결의. 2025Q3~2026Q2 배당 확인. 4/4.
- 출처:
  - https://koreadividend.kr/KR7005931001

### pension
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "삼성전자우 국민연금 대량보유". 우선주 단독 지분 추세 미확인.
- 출처:
  - 확인 불가

### purpose
- 점수 제안(0-100): 50
- 근거: 우선주 대상 5%룰 대량보유보고(투자목적) 미확인 → 보고 없음 중립.
- 출처:
  - 확인 불가

## [055550] 신한지주
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 분기배당 유지·자사주 매입·소각 진행. 2025Q3~2026Q2 환원 이벤트 확인. 4/4.
- 출처:
  - https://www.datatooza.com/article/20260423135249809552ef307085_80
  - https://www.getnews.co.kr/news/articleView.html?idxno=868506

### pension
- 점수 제안(0-100): 60
- 근거: 국민연금 9.01%→8.97%(명부 조정)→9.19%(순매수). 연속 실질 순증으로 단정 어려워 보수.
- 출처:
  - https://www.datatooza.com/article/20260720171233769352ef31cf03_80

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 2025-03 단순투자 변경 후 유지 재확인.
- 출처:
  - https://www.joongangenews.com/news/articleView.html?idxno=414366

## [069960] 현대백화점
- 섹터: retail

### execution
- 점수 제안(0-100): 50
- 근거: 결산배당(연1회) 1건 + 2026Q2 자사주 소각 1건. 2/4.
- 출처:
  - https://www.asiae.co.kr/article/2026021114555007157

### pension
- 점수 제안(0-100): 58
- 근거: 국민연금 12.70%(2026-03)→13.49%(2026-06). 직전 감소 후 1분기 증가라 상승추세(70+) 미충족.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680784

### purpose
- 점수 제안(0-100): 30
- 근거: 최대주주 현대지에프홀딩스 대량보유보고(2026-07-03) 보유목적 경영권 영향.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=681234

## [024110] 기업은행
- 섹터: financial

### execution
- 점수 제안(0-100): 50
- 근거: 2026Q1 결산배당 + 2026Q2 분기배당 도입. 2025Q3·Q4 미확인. 2/4. 자사주 구조적 제약.
- 출처:
  - https://www.mk.co.kr/news/economy/11993807

### pension
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "기업은행 국민연금 대량보유상황보고서 2026".
- 출처:
  - 확인 불가

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "기업은행 국민연금 보유목적 2025".
- 출처:
  - 확인 불가

## [034730] SK
- 섹터: holding

### execution
- 점수 제안(0-100): 50
- 근거: 2025Q3 중간배당, 2026Q2 결산배당 기준. 2025Q4·2026Q1 미확인. 2/4.
- 출처:
  - https://sk-inc.com/kr/ir/faq.aspx
  - https://news.einfomax.co.kr/news/articleView.html?idxno=4399121

### pension
- 점수 제안(0-100): 35
- 근거: 국민연금 수분기 상승 후 최근 분기 7.68%→7.37% 하락 전환.
- 출처:
  - https://stockhub.kr/national-pension

### purpose
- 점수 제안(0-100): 30
- 근거: 최대주주 최태원 대량보유보고(2026-04-13) 보유목적 경영권 영향.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20260413002952

## [032830] 삼성생명
- 섹터: insurance

### execution
- 점수 제안(0-100): 25
- 근거: 연 1회 결산배당만(2025년 5300원). 자사주 소각 계획 없음. 1/4.
- 출처:
  - https://www.businesspost.co.kr/BP?command=article_view&num=432714

### pension
- 점수 제안(0-100): 45
- 근거: 국민연금 7.07%대→6.85% 횡보·소폭 하락. flat 근접 보수 채점.
- 출처:
  - https://www.ceoscoredaily.com/page/view/2026071410253328716

### purpose
- 점수 제안(0-100): 30
- 근거: 최대주주 삼성물산 대량보유보고(2025-11-07) 보유목적 경영권 영향.
- 출처:
  - https://www.awakeplus.co.kr/data/view/20251107000568

## [316140] 우리금융지주
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 분기배당 유지·자사주 매입·소각(상반기 2000억 등). 2025Q3~2026Q2 환원 확인. 4/4.
- 출처:
  - https://www.asiae.co.kr/article/2026072416255125663
  - https://dealsite.co.kr/articles/160832

### pension
- 점수 제안(0-100): 50
- 근거: 국민연금 6.7~6.8%대 횡보. 블랙록 확대는 연금 추세와 별개 → 보합.
- 출처:
  - https://www.mk.co.kr/news/stock/11961497
  - https://activeholders.com/companies/316140

### purpose
- 점수 제안(0-100): 100
- 근거: 최신 대량보유 블랙록(2026-02) 단순투자. 국민연금도 단순투자.
- 출처:
  - https://activeholders.com/companies/316140

## [138930] BNK금융지주
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 분기배당·결산배당·자사주 매입·소각이 최근 4개 성과분기에서 확인. 4/4.
- 출처:
  - https://www.getnews.co.kr/news/articleView.html?idxno=868506

### pension
- 점수 제안(0-100): 25
- 근거: 국민연금 8.57%(2025-04)→7.57%(2026-04) 감소.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680269

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 대량보유보고(2026-04-27) 보유목적 단순투자.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=680269

## [029780] 삼성카드
- 섹터: financial

### execution
- 점수 제안(0-100): 25
- 근거: 연 1회 결산배당만. 자사주 단기계획 없음. 최근 4분기 중 1분기만 이벤트. 1/4.
- 출처:
  - 확인 불가; 검색 키워드: "삼성카드 결산배당 2026 이사회"

### pension
- 점수 제안(0-100): 50
- 근거: 국민연금 6.02% 수준, 2024-10 이후 추가 변동 보고 없어 flat.
- 출처:
  - https://activeholders.com/companies/029780

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 약식 보고(단순추가취득/처분) — 단순투자 범주. 경영참여 전환 미확인.
- 출처:
  - https://activeholders.com/companies/029780

## [005380] 현대차
- 섹터: auto

### execution
- 점수 제안(0-100): 100
- 근거: 분기배당(분기 2500원대) + 자사주 매입·소각 프로그램 병행. 4/4.
- 출처:
  - 확인 불가; 검색 키워드: "현대차 분기배당 자사주 소각 2026"

### pension
- 점수 제안(0-100): 75
- 근거: 국민연금 지분율 다년간 우상향(7.13%→7.76%대). 순매수 기조.
- 출처:
  - https://stockhub.kr/national-pension

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 일반투자 전환 12개사 명단에 미포함 — 단순투자 유지로 판단(교차미완).
- 출처:
  - 확인 불가; 검색 키워드: "현대차 국민연금 대량보유 보유목적 2026"

## [086790] 하나금융지주
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 최근 4분기 배당+자사주 매입·소각 병행 확인. 4/4.
- 출처:
  - 확인 불가; 검색 키워드: "하나금융지주 분기배당 자사주 2026"

### pension
- 점수 제안(0-100): 50
- 근거: 보유주식수 소폭 감소하나 소각 분모로 지분율 표면 상승 → 분모효과로 flat(50).
- 출처:
  - https://stockhub.kr/national-pension

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 단순투자 유지로 판단(일반투자 전환 12개사 미포함, 교차미완).
- 출처:
  - 확인 불가; 검색 키워드: "하나금융지주 국민연금 보유목적 2026"

## [009150] 삼성전기
- 섹터: electronics

### execution
- 점수 제안(0-100): 25
- 근거: 연 1회 결산배당만. 최근 4분기 중 1분기만 이벤트. 1/4.
- 출처:
  - 확인 불가; 검색 키워드: "삼성전기 결산배당 2026"

### pension
- 점수 제안(0-100): 25
- 근거: 국민연금 10.92%→9.87% 감소(장내매도).
- 출처:
  - 확인 불가; 검색 키워드: "삼성전기 국민연금 지분율 2026 2분기"

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 보유목적 단순투자로 관례 분류·경영참여 전환 보도 미확인(교차미완).
- 출처:
  - 확인 불가; 검색 키워드: "삼성전기 국민연금 대량보유 보유목적"

## [028260] 삼성물산
- 섹터: holding

### execution
- 점수 제안(0-100): 25
- 근거: 연 1회 결산배당·연 1회 자사주 소각이 Q1에 집중. 최근 4분기 중 2026Q1만. 1/4.
- 출처:
  - 확인 불가; 검색 키워드: "삼성물산 자사주 소각 배당 2026"

### pension
- 점수 제안(0-100): 75
- 근거: 국민연금 지분율 우상향(7%대→8%대). 순증 추세.
- 출처:
  - https://stockhub.kr/national-pension

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 삼성물산 보유목적 일반투자(단순투자에서 상향). 일반투자=100 구간.
- 출처:
  - 확인 불가; 검색 키워드: "삼성물산 국민연금 일반투자 전환"

## [105560] KB금융
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 2025Q3~2026Q2 배당·자사주 매입·소각 이사회 결의 확인. 4/4.
- 출처:
  - https://www.etnews.com/20260723000322
  - https://kind.krx.co.kr/external/2026/04/23/000504/20260423001397/11332.htm

### pension
- 점수 제안(0-100): 30
- 근거: 국민연금 절대 보유주식수 연속 감소. 지분율↑는 소각 분모효과 → 감소로 판정.
- 출처:
  - https://www.sec.gov/Archives/edgar/data/1445930/000119312526309457/d171931d6k.htm

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 2026-07-17 보유목적 일반투자→단순투자 변경.
- 출처:
  - https://news.einfomax.co.kr/news/articleView.html?idxno=4420596

## [175330] JB금융지주
- 섹터: financial

### execution
- 점수 제안(0-100): 100
- 근거: 최근 4분기 배당+자사주 이벤트 확인. 4/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=659815
  - https://www.mt.co.kr/finance/2026/07/23/2026072318222663462

### pension
- 점수 제안(0-100): 50
- 근거: 국민연금 6.43%대 횡보. flat.
- 출처:
  - https://www.jbfg.com/ko/governance/shareholder/structure.do

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "JB금융지주 국민연금 대량보유상황보고서 보유목적".
- 출처:
  - 확인 불가

## [015760] 한국전력
- 섹터: utility

### execution
- 점수 제안(0-100): 25
- 근거: 연 1회 결산배당만(2025년 1542원, 2026-03 주총). 1/4.
- 출처:
  - https://www.digitaltoday.co.kr/news/articleView.html?idxno=645581

### pension
- 점수 제안(0-100): 35
- 근거: 국민연금 7.90%→6.88% 감소 확인. 이후 반등 언급 혼조 → 보수 감소.
- 출처:
  - 확인 불가; 검색 키워드: "한국전력 국민연금 지분율 2026"

### purpose
- 점수 제안(0-100): 30
- 근거: 국민연금 보유목적 일반투자 변경 보도(탈석탄 전략). 시점 stale 우려·교차미완.
- 출처:
  - http://www.impacton.net/news/articleView.html?idxno=2896

## [032640] LG유플러스
- 섹터: telecom

### execution
- 점수 제안(0-100): 100
- 근거: 중간배당·자사주 매입·소각·기말배당 등 2025Q3~2026Q2 이벤트 확인. 4/4.
- 출처:
  - https://news.lguplus.com/21143
  - https://news.lguplus.com/21757

### pension
- 점수 제안(0-100): 30
- 근거: 국민연금 8.42%→7.38%→6.79% 최근 연속 감소.
- 출처:
  - https://activeholders.com/companies/032640
  - https://news.tf.co.kr/read/economy/2343254.htm

### purpose
- 점수 제안(0-100): 100
- 근거: 국민연금 보유목적 단순투자(보고사유 단순 추가취득/처분).
- 출처:
  - https://activeholders.com/companies/032640

## [000270] 기아
- 섹터: auto

### execution
- 점수 제안(0-100): 50
- 근거: 연 1회 결산배당 + 자사주 매입 정례. 최근 4분기 중 2분기 이벤트. 2/4.
- 출처:
  - https://www.bloter.net/news/articleView.html?idxno=655286

### pension
- 점수 제안(0-100): 50
- 근거: 국민연금 6.61% 수준 약 2년 횡보.
- 출처:
  - https://goinsider.kr/stock/00106641

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "기아 국민연금 대량보유상황보고서 보유목적 2026". 2021년 목적변경은 stale.
- 출처:
  - 확인 불가

## [088350] 한화생명
- 섹터: insurance

### execution
- 점수 제안(0-100): 0
- 근거: 2024년부터 배당 중단·자사주 소각 미실행. 최근 4분기 환원 이벤트 0/4.
- 출처:
  - https://www.thebell.co.kr/front/newsview.asp?key=202605121524263000105929

### pension
- 점수 제안(0-100): 50
- 근거: 국민연금 5.33%→5.57%이나 이후 1년 정체 → +2분기 연속 증가 미충족, flat.
- 출처:
  - https://goinsider.kr/stock/00113058

### purpose
- 점수 제안(0-100): _____
- 근거: 확인 불가; 검색 키워드: "한화생명 국민연금 대량보유상황보고서 보유목적".
- 출처:
  - 확인 불가

---

## B_FINAL6_DEEP

최종 제안 6종 심층(공시·환원·연기금·투자목적·리스크).

### DEEP [005830] DB손해보험
- 섹터: financial
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [105560] KB금융
- 섹터: financial
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [006040] 동원산업
- 섹터: consumer_staples
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [271560] 오리온
- 섹터: consumer_staples
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [021240] 코웨이
- 섹터: consumer_quality
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [005440] 현대지에프홀딩스
- 섹터: holding_company
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [005930] 삼성전자
- 섹터: semiconductor
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

### DEEP [032640] LG유플러스
- 섹터: telecom
- 공시/지배구조: _____
- 자사주·배당·환원: _____
- 연기금·수급: _____
- 투자목적: _____
- 리스크: _____
- 출처:
  - 

---

## C_T2_EVENTS

제도 이벤트 발생 여부. `fired`는 true/false만.
**`근거`는 fired=false여도 한 줄 필수.** `_____`·빈칸이면 업로드 실패(영역 empty).
true는 1차 출처(관보·MSCI 공식·금융위/KASB 고시) URL이 있을 때만.
완성 예 (복붙 금지 — 형식만 참고):
- fired: false
- 근거: as_of 기준 MSCI 공식 DM 편입 발표 없음(워치리스트·전망만으로는 미확정)
- 출처:
  - 확인 불가; 검색 키워드: "MSCI Korea DM inclusion official announcement"

### EVENT [commercial_code_enforcement_decrees]
- fired: false
- 근거: as_of 2026-07-24 기준 상법 관련 시행령·시행규칙의 관보 게재(확정)를 확인하지 못함. 입법예고·보도만으로는 미확정.
- 출처:
  - 확인 불가; 검색 키워드: "상법 시행령 관보 주주환원 2026"

### EVENT [msci_dm_index_inclusion_confirmed]
- fired: false
- 근거: as_of 2026-07-24 기준 MSCI 공식 DM 편입 발표 없음. 워치리스트·전망 보도는 확정으로 보지 않음.
- 출처:
  - 확인 불가; 검색 키워드: "MSCI Korea developed market inclusion announcement 2026"

### EVENT [ifrs18_domestic_adoption_schedule_confirmed]
- fired: false
- 근거: as_of 2026-07-24 기준 금융위·한국회계기준원의 IFRS18 국내 도입 일정 확정 고시를 확인하지 못함. 검토·의견수렴만으로는 미확정.
- 출처:
  - 확인 불가; 검색 키워드: "IFRS18 국내 도입 일정 금융위원회 고시"

---

## D_THESIS

**`근거` 필수.** damage=false여도 `_____`면 업로드 실패.
완성 예: damage: false / 근거: as_of 기준 상법·밸류업 제도 후퇴·유예 확정 공시 없음

### THESIS
- damage: false
- 근거: as_of 2026-07-24 기준 주주환원·지배구조·밸류업 제도 환경의 확정적인 후퇴·유예·철회 공시를 확인하지 못함. 개별 실적·주가 변동만으로는 논지 훼손으로 보지 않음.
- 출처:
  - 확인 불가; 검색 키워드: "상법개정 주주환원 후퇴 유예 2026"

---

## E_TARGET_VALUATION

제안 6종 목표가/PBR. target_portfolio 자동 변경 금지.
`pbr_max`는 배수 숫자만(예: `0.75`), `target_price`는 원 단위 숫자만(예: `48000`).
둘 중 최소 1개는 숫자. `배`/`원`/쉼표/범위(~)/증권사 주석은 근거 칸에만.
**`펀더멘털 사유`·`근거`·출처 URL≥1 필수.** `_____`면 해당 종목 파싱 실패.
A만 채우고 E를 비우면 결재함에서 목표가 영역이 empty로 뜹니다 (E-only 보충 요청서 또는 `WEEKLY_QUAL_CDE_PROMPT` 사용).

### TARGET [005830] DB손해보험
- pbr_max: 1.4
- target_price: 220000
- 펀더멘털 사유: 위험손해율 개선·보험손익 회복·ROE 업종 평균 상회 논지.
- 근거: 2026.7 증권사 목표가 컨센서스 약 21.9만원대. 기존 승인안 22만원 부합(초안·재검증).
- 출처:
  - https://www.newspim.com/news/view/20260710001001
  - https://www.kfenews.co.kr/news/articleView.html?idxno=660618

### TARGET [105560] KB금융
- pbr_max: 1.2
- target_price: 200000
- 펀더멘털 사유: 2분기 호실적·CET1 여력·자사주 완전 환원 등 밸류업 모멘텀.
- 근거: 컨센서스 약 19.6만~20.2만원. 기존 21만원 대비 보수적으로 20만원(재검증).
- 출처:
  - https://kr.investing.com/equities/kb-financial-group-consensus-estimates
  - https://www.inews24.com/view/1988263

### TARGET [006040] 동원산업
- pbr_max: 0.65
- target_price: 45000
- 펀더멘털 사유: 식품 가공·유통 안정성·저PBR. 단기 원가·관세 부담.
- 근거: 다올 등 목표가 하향 후 4.5만원대. 현재가와 근접해 보수안 유지(초안).
- 출처:
  - https://www.newspim.com/news/view/20260423000788
  - http://www.dailyinvest.kr/news/articleView.html?idxno=70635

### TARGET [271560] 오리온
- pbr_max: 1.6
- target_price: 165000
- 펀더멘털 사유: 중국·러시아 법인 성장·주주환원 강화.
- 근거: 증권사 평균 목표가 약 16.3만~16.7만원. 16.5만원 유지(초안).
- 출처:
  - https://stockanalysis.com/quote/krx/271560/forecast/
  - https://wcomp.fnguide.com/CompanyInfo/Snapshot?cmp_cd=271560

### TARGET [021240] 코웨이
- pbr_max: 2.27
- target_price: 130000
- 펀더멘털 사유: 렌탈 현금흐름·해외 성장·환원. 주가 재평가 반영해 보수화.
- 근거: 컨센서스 약 12.2만~13.7만원. 한화 15만원은 상단으로 보고 13만원 채택(재검증).
- 출처:
  - https://kr.investing.com/equities/coway-consensus-estimates
  - https://stockhub.kr/stock/021240

### TARGET [005440] 현대지에프홀딩스
- pbr_max: 0.7
- target_price: 20000
- 펀더멘털 사유: 지주 체제 전환·자사주·배당 확대·NAV 할인 축소 기대.
- 근거: 최근 목표가 약 1.975만~2.0만원. 2만원 유지(초안).
- 출처:
  - https://www.newspim.com/news/view/20260716000130
  - https://news.nate.com/view/20260623n06021

### TARGET [005930] 삼성전자
- pbr_max: _____
- target_price: 480000
- 펀더멘털 사유: HBM·서버 메모리 업사이클·2분기 어닝 서프라이즈. 익절 상한 초안(매수 추천 아님).
- 근거: 목표가 컨센서스 편차 큼. 하단~중간 48만원 보수 채택. 단기 변동성 유의.
- 출처:
  - https://www.newspim.com/news/view/20260708000534
  - https://www.dt.co.kr/article/12074290

### TARGET [032640] LG유플러스
- pbr_max: _____
- target_price: 20000
- 펀더멘털 사유: AIDC/B2B·주주환원수익률 통신 3사 중 상위권 논지.
- 근거: 최근 목표가 평균·중앙값 약 1.98만~2.0만원. 2만원 유지(초안).
- 출처:
  - https://stockhub.kr/stock/032640
  - https://www.newspim.com/news/view/20260713000221

---

## F_QUANT_EVENTS

정량 이벤트 감시(수동). **CECS/점수는 자동 변경되지 않음** — 재채점 검토 신호만.
PyKRX/DART로는 컨센서스 EPS·목표가·등급을 자동 수집할 수 없음 (`docs/CONSENSUS_DATA_FEASIBILITY.md`).

event_id 허용값: `earnings_surprise` | `rating_downgrade` | `target_gap_narrowed`
해당 없으면 `event_id: _____` 로 두세요. 임계값(SUE/%)은 TODO.

### SIGNAL [005830] DB손해보험
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [105560] KB금융
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [006040] 동원산업
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [271560] 오리온
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [021240] 코웨이
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [005440] 현대지에프홀딩스
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [005930] 삼성전자
- event_id: _____
- note: _____
- 출처:
  - 

### SIGNAL [032640] LG유플러스
- event_id: _____
- note: _____
- 출처:
  -
