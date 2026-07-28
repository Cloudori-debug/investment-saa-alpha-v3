# Multi-Asset Trigger Portfolio — MVP 명세서

> **버전:** **v1.0 FROZEN** · **동결일:** 2026-06-19  
> **실운용 승인 (최종 게이트):** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) — 현재 **YELLOW / ETF_ONLY**  
> **Dry-run:** [DRY_RUN_LOG_SCHEMA.md](DRY_RUN_LOG_SCHEMA.md)  
> **목표:** 규칙 기반 자산배분·Alpha 스크리닝·사람 승인 실행 보조 (자동매매 없음)

**문서 역할:** 본 문서 = **개발 스펙**. 실거래·매매 허용 여부는 **ACCEPTANCE_CRITERIA.md**만 따른다.

**동결 정책:** v1.0 이후 신규 기능 추가 중단. 버그 수정·AC/dry-run·문서 정합성만 허용.

---

## 1. MVP 범위 요약

| 레벨 | 모듈 | MVP 상태 | 설명 |
|------|------|----------|------|
| L1 | 나침반 (Compass) | ✅ 완료 | Tier1 + Tier2 → 레짐·4축·방향 |
| L2 | SAA/TAA + 분해 | ✅ 완료 | 자산군 목표 → 종목 target |
| L3 | KOSPI Alpha Screener | ✅ 완료 | Q/V/M 팩터·PIT gate·후보 CSV |
| L4 | 승인 브릿지 | ✅ 완료 | checklist → target diff (수동 반영) |
| L5 | 데이터 갱신 | ✅ 완료 | PyKRX bulk + DART enrich |
| L6 | 실행·트리거 | ✅ 완료 | market_triggers + asset_triggers |
| L7 | 검증·AI 내보내기 | ✅ 완료 | system_health + ai_export_bundle |
| L8 | 백테스트 | ✅ Lite | 레짐·Alpha quintile |

**의도적 제외:** 자동매매, 증권사 API, `target_portfolio.csv` 자동 덮어쓰기, ML 수익률 예측

---

## 2. 아키텍처·파이프라인

```
[ data/ 입력 ] ──► run_full_pipeline() ──► [ outputs/ ]
       │                    │
       │    ┌───────────────┼───────────────┐
       │    ▼               ▼               ▼
       │  Compass        Alpha          실행층
       │  regime+TAA    screener      gap+trigger+action
       │    │               │               │
       └────┴───────────────┴───────────────┘
                         │
              system_health.json
              ai_export_bundle.json (UI 생성)
```

**엔트리포인트**

| 명령 | 역할 |
|------|------|
| `python -m src.main` | 전체 파이프라인 |
| `python -m src.compass_main` | 나침반만 |
| `python -m src.alpha.alpha_main` | Alpha만 |
| `python -m src.data_refresh.refresh_main --bulk` | PyKRX 일괄 |
| `streamlit run app.py` | 운용 UI |

---

## 3. 모듈별 필수 지표·데이터·로직

### 3.1 나침반 — Tier1 (시장 지표)

**입력:** `data/market_indicators.csv` (최신 1행)  
**규칙:** `data/compass_rules.yaml`  
**Provenance:** `data/market_data_provenance.json` (갱신 시 자동)

#### 3.1.1 Tier1 필드 — MVP+ 현재 (v1.0)

| 필드 | Compass | 자동 수집 (Current) | Fallback |
|------|---------|---------------------|----------|
| kospi, kospi_200ma, kospi_recent_high | ✅ | PyKRX KOSPI 지수 | 수동 CSV |
| sp500, sp500_recent_high | ✅ | Yahoo ^GSPC | 이전값·수동 |
| vix | ✅ | Yahoo ^VIX | 이전값·수동 |
| usdkrw | ✅ | Yahoo KRW=X → Frankfurter | 수동 |
| oil_brent | ✅ | Yahoo BZ=F | 수동 |
| gold | ✅ | Yahoo GC=F | 수동 |
| korea_10y | ✅ | PyKRX 국채 → macro_tier2 | Tier2·수동 |
| foreign_flow_3d | ✅ | PyKRX 외국인 순매수 | neutral·수동 |
| regime | override | **수동만** | NEUTRAL=산출값 |

> **Legacy (MVP 초기):** vix/usdkrw/oil/gold/sp500은 수동 CSV만 사용. MVP+ 이후 `refresh_all_market_indicators()`가 자동 갱신. **API 실패·stale·결측 시** 이전값 유지 또는 수동 입력 — fail-open 금지(trigger 비활성).

#### 3.1.2 Manual regime override

| 컬럼 | 필수 | 설명 |
|------|------|------|
| `regime` | override 시 | NEUTRAL/AUTO → 산출 레짐 |
| `regime_override_reason` | ✅ | 사유 |
| `regime_set_date` | ✅ | 입력일 |
| `regime_expires_date` | 권장 | **초과 시 산출 레짐 자동 적용** |

운용 검증: [ACCEPTANCE_CRITERIA.md AC-05](ACCEPTANCE_CRITERIA.md)

#### 3.1.3 API 자격 (KRX / DART)

| 자격 | 필요 조건 | 용도 |
|------|----------|------|
| **KRX ID/PW** | PyKRX **bulk**·`import_pykrx_stock()` 경로 | universe/prices/fundamentals 일괄, KOSPI 지수·외국인 flow |
| **없이 가능** | 환경·엔드포인트에 따라 Yahoo만으로 Tier1 글로벌 지표 | vix/sp500/gold/oil/usdkrw |
| **DART_API_KEY** | ✅ DART enrich | ROE/부채/OCF·usable_from_date |

본 프로젝트는 bulk 수집·`refresh_all_market_indicators`의 KOSPI/flow/국채 경로에서 **KRX 자격을 요구**한다. 공개 조회만 쓸 경우에도 코드상 `check_krx_credentials`가 호출될 수 있음 — **설정 탭 또는 환경변수** 권장.

**로직 (`regime_engine.py`, `economic_phase.py`):**

1. 4축 점수: growth, inflation, liquidity, risk_appetite (−1~+1)
2. Tier2 있으면 30% blend (`macro_tier2.csv`)
3. `computed_regime`: RISK_ON → YELLOW_STABLE → CAUTION → RISK_OFF → CRISIS
4. CSV `regime`과 다르면 **수동 override** → `applied_regime`
5. 출력: `compass_regime.json`, `compass_report.md`

### 3.2 나침반 — Tier2 (매크로, 선택)

**입력:** `data/macro_tier2.csv`

| 필드 | 용도 |
|------|------|
| pmi_kr, pmi_us | 성장 blend |
| cpi_kr_yoy, cpi_us_yoy | 인플레이션 |
| yield_spread_2y10y, hy_oas_bp | 유동성·리스크 |
| real_rate_kr | 인플레이션 |

없으면 `tier2_used=false` — Tier1만으로 동작.

### 3.3 SAA / TAA

**입력:** `saa_profiles.yaml` + Compass 결과  
**로직:** `portfolio_builder.py`

```
final_target = SAA_base + regime_tilt + phase_tilt  (min/max clamp)
```

**출력:** `target_asset_allocation.csv`, `generated_target_portfolio.csv`

프로필: `defensive_balanced`(alias balanced), `capital_preservation`, `active_growth`

### 3.4 KOSPI Alpha Screener

**입력**

| 파일 | 필수 컬럼·역할 |
|------|----------------|
| universe.csv | ticker, market, sector, flags (관리/거래정지 등) |
| fundamentals.csv | ROE, PER, PBR, debt, OCF, FCF, **usable_from_date** (PIT) |
| prices.csv | close, momentum, liquidity, 52w high |
| universe_filter.yaml | 유동성·시총·data_gate |
| alpha_scoring.yaml | quality/valuation/momentum 가중치 |

**로직 흐름**

1. `filter_universe` — 유동성·블랙리스트
2. `apply_data_gate` — PIT, stale 120일
3. `score_factors` + `apply_penalties` + `assign_grades`
4. `review_holdings` — KEEP/WATCH/TRIM/REPLACE
5. `constraints` — kr_alpha 예산·섹터 vs Compass
6. **자동 target 덮어쓰기 없음**

**데이터 소스**

| 지표 | PyKRX bulk | DART enrich |
|------|------------|-------------|
| PER, PBR, 배당 | ✅ | — |
| ROE, ROA, 부채, OCF, FCF | — | ✅ |
| usable_from_date | — | ✅ (공시일+1) |
| 가격·모멘텀 | ✅ prices.csv | — |

### 3.5 실행·트리거·Gap

| 단계 | 입력 | 출력 | data_gate 영향 |
|------|------|------|----------------|
| 종목 Gap | positions + targets | current_vs_target.csv | — |
| 자산군 Gap | positions + Compass | portfolio_gap.csv | — |
| 트리거 | market + trigger_rules | trigger_alerts.md | — |
| 리스크 | portfolio_policy | hard stop → Trim | — |
| 종목 실행 | gaps + alerts | trade_actions.csv | RED→No trade |
| 자산군 실행 | group gaps | portfolio_actions.md | RED→NoTrade |

**트리거 구현 상태:** `market_triggers` (KOSPI pullback, VIX, USD/KRW, foreign flow) ✅  
**구현:** `trigger_rules.yaml` `asset_triggers` — domestic/global beta, sk_hynix, gold, dollar (`src/trigger_conditions.py`)

### 3.6 Data Gate (통합)

| 체계 | 기준 | 사용처 |
|------|------|--------|
| Portfolio gate | positions/target + regime | 원천 |
| Alpha gate | fundamentals PIT/stale | 원천 |
| **Effective gate** | `merge_data_gates(portfolio, alpha)` | trade_actions, decision_log |

설정: `portfolio_policy.yaml` → `data_gate_policy.merge_alpha_gate`

---

## 4. 검증 (system_health)

**모듈:** `src/validation/system_health.py`  
**UI:** Streamlit **검증** 탭  
**출력:** `outputs/system_health.json`

검증 항목:

- 필수 입력 파일 존재
- Tier1 필드 0/결측 (Compass 사용 필드)
- Tier2 커버리지
- Alpha fundamentals/prices 커버리지 %
- portfolio weight 합 100
- outputs 산출물 존재
- compass_regime / gpt_context / decision_log 정합

**종합 판정:** fail > warn > pass

전체 분석 실행 시 자동으로 `system_health.json` 갱신.

---

## 5. AI 교차 검증 내보내기

**모듈:** `src/validation/ai_export.py`  
**UI:** Streamlit **AI 내보내기** 탭

**번들 내용 (`ai_export_bundle.json`):**

- validation_prompt.md (검증 지시문)
- health_report
- gpt_context, compass_regime
- decision_log 마지막 행
- compass/alpha/daily/trigger 리포트
- 주요 CSV 요약 (top10 candidates 등)
- data_inputs_snapshot
- known limitations

**다운로드:** JSON 단독 / ZIP (프롬프트+리포트 포함)

---

## 6. 현재 개발 진행·샘플 데이터 검증 결과

### 6.1 완료된 기능

- [x] Compass P0 v1.0 + Tier2 blend
- [x] SAA/TAA + target decomposer
- [x] Alpha full pipeline + holdings review
- [x] Approval checklist + target bridge (수동 승인)
- [x] PyKRX bulk + DART enrich
- [x] Streamlit: Today, Alpha, 승인, 설정, 데이터, **검증**, **AI 내보내기**
- [x] 레짐·Alpha lite 백테스트
- [x] user_secrets (KRX/DART 키)
- [x] system_health + ai_export

### 6.2 샘플 환경 관찰 — **MVP+ 이전 기록 (2026-06-17)**

> 아래는 MVP+ 구현 **전** 샘플 CSV 기준 스냅샷. **현재 코드 상태와 혼동하지 말 것.**

| 항목 | 당시 상태 | MVP+ 이후 |
|------|----------|-----------|
| sp500, gold | 0 (미입력) | Yahoo 자동 + Compass 4축 |
| regime | YELLOW_STABLE 수동 | 만료·reason 메타 추가 |
| Alpha universe | ~15종 샘플 | bulk 검증 필요 |

**MVP+ 이후** `refresh_all_market_indicators` + `system_health`로 **재검증 필수**.

### 6.3 MVP+ 구현 (v1.0에 포함)

1. ✅ `market_indicators` VIX·SP500·금·유가·환율 — Yahoo + KOSPI/국채/외국인 PyKRX (`refresh_all_market_indicators`)
2. ✅ `asset_triggers` — gold/dollar/sk_hynix/domestic/global beta
3. ✅ Portfolio ↔ Alpha data_gate 통합 (`unified_data_gate.py`)
4. ✅ sp500/gold Compass 4축 반영 (`economic_phase.py`)

---

## 7. Streamlit 메뉴 맵

| 메뉴 | 기능 |
|------|------|
| Today | 레짐·Alpha 후보 요약 |
| 나침반 | compass_report.md |
| Alpha | 후보·제외·보유 리뷰 |
| 승인·Target | checklist → target diff |
| 자산군 배분/Gap | TAA 결과 |
| 종목 Gap/실행 | trade_actions |
| 백테스트 | 레짐 + Alpha lite |
| **운용승인** | AC + dry-run + scope |
| **AI 내보내기** | 교차 검증 번들 |
| 데이터 | refresh / PyKRX / DART |
| 설정 | API 키 |

**사용법:** [USER_GUIDE.md](USER_GUIDE.md)

---

## 8. 테스트

```powershell
pytest tests/ -q
```

포함: compass, alpha, data_refresh, pykrx, dart, user_secrets, **system_health**

---

## 9. 파일 경로 Quick Reference

```
data/
  market_indicators.csv    # Tier1
  macro_tier2.csv          # Tier2 (선택)
  universe.csv, fundamentals.csv, prices.csv  # Alpha
  compass_rules.yaml, saa_profiles.yaml
  local/user_secrets.json  # KRX/DART (gitignore)

outputs/
  compass_regime.json
  gpt_context.json
  system_health.json
  ai_export_bundle.json

src/
  full_pipeline.py
  compass/
  alpha/
  data_refresh/
  validation/system_health.py, ai_export.py
  ui/health_panel.py, export_panel.py
```

---

*본 문서 = 개발 스펙 v1.0 FROZEN. 실운용 판단은 [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)만 최종 게이트.*
