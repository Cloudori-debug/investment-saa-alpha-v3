# 경제 나침반 백테스트 — 데이터 가용성 확인 결과

> SPEC: [`ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_SPEC.md`](ECONOMIC_COMPASS_BACKTEST_DATA_CHECK_SPEC.md)  
> 원칙: 코드/`data` 미변경 · 임시 프로브만 실행 후 삭제.

## 요약표

| 항목 | 결과 | 비고 |
|---|---|---|
| FRED_API_KEY 설정 여부 | **설정됨** | `data` 시크릿(`fred_api_key`) + `apply_secrets_to_env` 후 env 반영. `.env` 단독에는 없음 |
| Yahoo 장기 이력(10년) | **가능** | `range=10y`·`range=3650d` 모두 성공. 운영 코드의 `400d`만으로 막힌 게 아니라 **호출 range만 키우면 됨** |
| KOSPI 지수 이력 — 로그인 | **이 환경에선 필요** · **자격증명 기설정으로 장기 fetch 성공** | 자격증명 없이 호출 시 실패; 적용 후 2015-01-02~2026-07-15 **2831행** |

**갈림길 판정: 셋 다 가용 → 방법 B(외부 장기데이터 백테스트) 본 스펙 작성 진행 가능.**

## 상세

### 1. FRED

- `src/settings/user_secrets.py`의 `fred_api_key`에 값 있음 → `FRED_API_KEY` env 주입 확인.
- 계정 신규 발급 불필요(이미 보유).

### 2. Yahoo Finance

GSPC(`^GSPC`) 형식 비교:

| URL 형식 | 결과 | n | 기간 |
|---|---|---|---|
| `interval=1d&range=3650d` (현재 코드 스타일 확장) | ok | 3650 | 2012-01-06 ~ 2026-07-15 |
| `interval=1d&range=10y` | ok | 2512 | 2016-07-18 ~ 2026-07-15 |
| `interval=1wk&range=10y` | ok | 524 | 2016-07-11 ~ 2026-07-15 |
| `interval=1d&range=max` | ok이나 n=168만 | — | (일봉 max는 Yahoo 측 샘플링으로 보임 — 장기 일봉엔 부적합) |

심볼별 `1wk&range=10y`: `^GSPC`, `^VIX`, `GC=F`, `BZ=F`, `KRW=X` **전부 성공**(각 n=524).

→ 권장: 백테스트용은 `range=10y` + `interval=1d`(또는 `3650d`). 운영 `_fetch_yahoo_chart` 기본 400d는 일일 스냅샷용으로 유지해도 됨(백테스트는 별도 호출).

### 3. KOSPI / KRX 로그인

- `check_krx_credentials()`는 벌크뿐 아니라 `market_indicators_refresh`·지수 OHLCV 경로도 `import_pykrx_stock`으로 공유.
- **자격증명 미적용**: `get_index_ohlcv_by_date` 실패(JSON 파싱·티커명 KeyError) + pykrx 쪽 로그인 경고.
- **자격증명 적용 후**: 단기 131행 / 장기 **2831행**(2015-01-02~2026-07-15) 성공.
- 결론: “지수라서 공개·로그인 불필요”는 **이 환경의 현재 pykrx 경로에서는 성립하지 않음**. 다만 시크릿에 KRX_ID/PW가 이미 있어 **방법 B용 KOSPI 이력은 확보 가능**.

## 다음

- 방법 B 본 스펙(백테스트 입력 구성·윈도우·나침반 재현·성과 지표) 작성 → Cursor 구현.
- 2단계 Turbulence 구현 게이트(60행 history)와는 **별트랙** — 이번 확인은 4단계/방법 B 전제.
