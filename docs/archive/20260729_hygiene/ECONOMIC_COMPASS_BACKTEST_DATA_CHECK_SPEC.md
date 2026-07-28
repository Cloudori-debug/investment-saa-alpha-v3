# 경제 나침반 백테스트 — 데이터 가용성 확인 (실행 명세서)

> ROADMAP: [`ECONOMIC_COMPASS_ROADMAP.md`](ECONOMIC_COMPASS_ROADMAP.md) — "검증 방법 후보" §B(외부 장기데이터 백테스트) 착수 전 확인 단계
> 목적: 4단계(실측 성과 검증)를 라이브 로그만으로 하면 기관급 표본까지 수년 걸림. 더 빠른 경로(과거 10~20년 데이터로 소급 백테스트)가 실제로 가능한지, **코드 구현 없이 확인만** 먼저 한다.
> 원칙: 이 단계는 조사·보고만. `data/`, `src/compass/` 등 실제 파일 수정 금지. 아래 3개 항목만 확인해 보고할 것.

## 확인 항목

### 1. FRED_API_KEY 설정 여부

- `src/data_refresh/fred_client.py`의 `_fred_get()`이 `api_key`가 비어있으면 `"FRED_API_KEY 미설정"` 에러를 반환하는 구조 확인함(코드 읽음).
- 확인할 것: 현재 환경(`.env`, `src/settings/user_secrets.py` 로드 경로, 또는 OS 환경변수)에 `FRED_API_KEY`가 이미 설정돼 있는지.
- 없다면: https://fred.stlouisfed.org/docs/api/api_key.html 에서 무료 가입 후 즉시 발급 가능하다는 점만 보고(발급 자체는 원장님 판단 필요 — Cursor가 임의로 계정 생성하지 말 것).

### 2. Yahoo Finance 장기 이력 fetch 가능 여부

- `src/data_refresh/external_market.py::_fetch_yahoo_chart()`는 현재 `range={range_days}d` 형식으로 호출하고 기본값 `range_days=400`(약 1년치)만 사용 중(코드 읽음, 라인 42-64).
- **실제 파일은 수정하지 말고**, 별도의 1회성 테스트 스크립트(예: `scripts/_tmp_check_yahoo_range.py`, 확인 후 삭제)로 아래 두 가지를 시도하고 결과만 보고:
  ```python
  # (a) 현재 형식 그대로 큰 값 시도
  url_a = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=3650d"
  # (b) Yahoo 표준 range 문자열 시도
  url_b = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1wk&range=10y"
  ```
  각각 응답에서 `timestamp` 배열 길이(=일수)와 최초/최근 날짜를 확인. 어느 형식이 실제로 10년치를 돌려주는지 보고.
- 대상 심볼: `^GSPC`(S&P500), `^VIX`(VIX), `GC=F`(금), `BZ=F`(유가), `KRW=X`(환율) — `_YAHOO_SYMBOLS` 딕셔너리에 이미 정의됨(코드 확인).
- 확인 후 테스트 스크립트는 삭제하거나 `archive/`로 이동(운영 코드에 영향 없게).

### 3. KOSPI 지수 장기 이력 — KRX 로그인 실제 필요 여부

- `src/data_refresh/pykrx_client.py::check_krx_credentials()`가 `KRX_ID`/`KRX_PW` 없으면 에러를 던지는 구조가 확인됨(코드 읽음, 라인 17-34).
- 확인할 것: 이 자격증명이 **KOSPI 지수 레벨 데이터**(`pykrx.stock.get_index_ohlcv_by_date` 류, 종목코드 "1001")에도 실제로 필요한지, 아니면 이 코드베이스의 다른 기능(개별종목 벌크수집 등)에만 필요하고 지수 데이터는 로그인 없이도 되는지.
- pykrx 라이브러리 자체는 통상 지수 데이터는 공개 데이터라 로그인 불필요한 경우가 많음 — 이 코드베이스가 굳이 게이트를 건 이유(예: 과거 남용 방지, 다른 API 세트 재사용 등)가 있는지도 확인되면 같이 보고.
- 확인 방법: `check_krx_credentials()`를 우회한 별도 테스트 스크립트로 `pykrx.stock.get_index_ohlcv_by_date("20150101", "20260716", "1001")` 같은 호출을 직접 시도(운영 코드 미변경, 임시 스크립트만).

## 보고 형식

아래 표 형태로 짧게 보고:

| 항목 | 결과 | 비고 |
|---|---|---|
| FRED_API_KEY 설정 여부 | 설정됨/미설정 | |
| Yahoo 장기 이력(10년) 실제 가능 여부 | 가능/불가능, 어느 URL 형식 | 실제 받아온 일수·기간 |
| KOSPI 지수 이력 — 로그인 필요 여부 | 필요/불필요 | |

이 확인 결과에 따라 다음이 결정됨:
- **셋 다 가능** → 외부 장기데이터 백테스트(로드맵 "방법 B") 본 스펙 작성 진행.
- **일부만 가능** → 가능한 지표만으로 부분 백테스트(예: KOSPI 로그인 필요해서 막히면 국채·VIX·환율 등 나머지만이라도 먼저 진행하는 방안 검토).
- **전부 불가능** → 로드맵 "방법 A"(라이브 로그 축적)만으로 진행, 4단계 타임라인 재확인.

## 절대 금지

- 이 단계에서 `data/compass_rules.yaml`, `src/compass/` 등 운영 코드/설정 변경 금지 — 순수 확인·보고만.
- FRED 계정 등 원장님 개인정보로 가입이 필요한 작업은 Cursor가 임의로 진행하지 말고 원장님께 안내만 할 것.
