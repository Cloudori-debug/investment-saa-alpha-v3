# 투자 나침반 — 사용설명서

> **Multi-Asset Trigger Portfolio** v1.0  
> 규칙 기반 자산배분·Alpha 스크리닝·**사람 승인** 실행 보조 도구

**이 프로그램이 하는 일:** 시장 상태 → 자산군 목표 → 종목 Gap → 매수/대기/축소 **권고** 생성  
**이 프로그램이 하지 않는 일:** 증권사 주문, 자동매매, `target_portfolio.csv` 자동 덮어쓰기

---

## 목차

1. [시작하기](#1-시작하기)
2. [매일 운용 흐름](#2-매일-운용-흐름-권장)
3. [Streamlit UI 메뉴](#3-streamlit-ui-메뉴)
4. [사이드바 — 전체 분석 실행](#4-사이드바--전체-분석-실행)
5. [데이터 준비](#5-데이터-준비)
6. [API 키 설정](#6-api-키-설정)
7. [데이터 갱신](#7-데이터-갱신)
8. [Alpha → Target 승인](#8-alpha--target-승인)
9. [운용 승인 · Dry-run](#9-운용-승인--dry-run)
10. [명령줄(CLI) 사용](#10-명령줄cli-사용)
11. [출력 파일 안내](#11-출력-파일-안내)
12. [자주 묻는 질문](#12-자주-묻는-질문)
13. [관련 문서](#13-관련-문서)

---

## 1. 시작하기 (CMD 없이 — 더블클릭만)

프로젝트 폴더: `C:\Cursor\multi_asset_trigger_portfolio\`

### 1.1 처음 한 번

| 순서 | 파일 | 설명 |
|------|------|------|
| 1 | **`설치.bat`** | Python 패키지 설치 (최초 1회, 1~3분) |
| 2 | **`투자나침반.bat`** | 런처 → **[1] UI 실행** (이후 매일 이것만) |

### 1.2 메인 런처 (`투자나침반.bat`)

**운용·설정·데이터·분석·승인은 모두 브라우저 UI에서 합니다.** bat는 UI를 여는 진입점만 제공합니다.

| 번호 | 기능 |
|------|------|
| 1 | **UI 실행** — 브라우저 운용 화면 (권장) |
| 2 | 설치 / 업데이트 |
| 0 | 종료 |

메뉴에 **DART/KRX 연결 상태**가 표시됩니다. 키는 UI **[설정]** 탭에서 저장하면 `data/local/user_secrets.json`에 기록되며, UI·bat가 동일 파일을 사용합니다.

### 1.3 (선택) 고급 bat — UI 없이 CLI만 쓸 때

| 파일 | 용도 |
|------|------|
| `UI실행.bat` | UI만 바로 실행 |
| `실행.bat` | 전체 분석만 |
| `PyKRX일괄수집.bat` | PyKRX bulk |
| `DART재무보강.bat` | DART enrich |
| `운용승인검증.bat` | AC 리포트 |

> Python 3.11+가 PC에 설치되어 있어야 합니다. bat은 **명령 프롬프트를 직접 열 필요 없이** 더블클릭으로 동작합니다.

### 1.4 (선택) 터미널에서 실행

고급 사용자용 — 일반 운용에는 bat만 사용하면 됩니다.

```powershell
pip install -e ".[dev,ui,data]"
streamlit run app.py
python -m src.main
```

---

## 2. 매일 운용 흐름 (권장)

```
[1] 대시보드 — 오늘 상태·Executable 요약 확인
      ↓
[2] (자동) daily_pipeline / 작업 스케줄러 — 없으면 ▶ 전체 분석
      ↓
[3] 종합 포트 → Gap·실행 — Buy-allowed / Trim 검토
      ↓
[4] 종합 포트 → 운용승인 — Scope · dry-run · 리서치 체크리스트
      ↓
[5] (선택) 알파 · 하케다카 50 — 리서치만 (실행 신호 아님)
      ↓
[6] 매매 후 positions 저장 → 재분석
```

> **UI 사용법 탭**에서 동일 내용을 인터랙티브로 볼 수 있습니다.

### 운용 승인 상태 읽는 법

| 표시 | 의미 | 일반적으로 허용 |
|------|------|----------------|
| **GREEN** | 데이터·gate 양호 | ETF·자산군 리밸런싱 검토 |
| **YELLOW** | 조건부 | ETF·자산군 OK, **kr_alpha 신규매수 금지** |
| **RED** | 중단 | 수정 전 거래 검토 금지 |

**Execution Scope** (더 중요):

| Scope | 의미 |
|-------|------|
| `ETF_ONLY` | 현금·채권·ETF·자산군 Gap 위주 (현재 흔한 상태) |
| `ETF_AND_BETA` | + 국내/글로벌 베타 (트리거 충족 시) |
| `FULL_WITH_ALPHA` | + kr_alpha (사람 승인 필수) |
| `NO_TRADE` | 점검만 |

> 실거래 허용 여부는 [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)가 최종 기준입니다.

---

## 3. Streamlit UI 메뉴

상단 가로 메뉴에서 탭을 선택합니다.

| 메뉴 | 용도 |
|------|------|
| **대시보드** | 일일 운용 허브 — 8단계·전체 분석·Executable 요약·AI ZIP |
| **사용법** | 빠른 시작·매일 5분·메뉴 맵·FAQ (인앱 가이드) |
| **나침반** | `compass_report.md` — 4축 점수, 레짐, TAA 근거 |
| **SAA·TAA** | SAA+TAA 자산군 목표 비중·배분 흐름 |
| **알파** | QVM-SR 스크리너 · Target 승인 · **하케다카 50** |
| **종합 포트** | 보유 편집 · Gap·실행 · 운용승인 · AI보내기 · 검증 |
| **백테스트** | 레짐·Alpha lite 히스토리 검증 |
| **설정** | DART·KRX API 키 · 데이터 갱신 · PyKRX/DART |

사이드바에 **오늘 상태**(Scope·dry-run·Gate)가 항상 표시됩니다.

---

## 4. 대시보드 — 전체 분석 실행

**대시보드** ② 단계에서 실행합니다 (사이드바가 아님).

| 항목 | 설명 |
|------|------|
| **시장지표** | 체크 시 분석 전 KOSPI·글로벌 갱신 |
| **target 분해** | 자산군 비중 → `generated_target_portfolio.csv` |
| **백테스트** | 히스토리 CSV 있으면 레짐·Alpha 백테스트 |
| **▶ 전체 분석 실행** | Compass + Alpha + Gap + 하케다카·리서치 + AC + dry-run |

자동화: `python scripts/daily_pipeline.py` 또는 Windows `MultiAssetDailyPipeline` (평일 08:00).

실행 후 자동 생성·갱신:

- `outputs/compass_regime.json`, `trade_actions.csv`, `gpt_context.json`
- `outputs/system_health.json`, `acceptance_report.json`
- `outputs/dry_run_log.jsonl` (영업일 1줄 추가)
- `outputs/run_manifest.json` (run_id)

---

## 5. 데이터 준비

### 5.1 반드시 있어야 하는 파일 (`data/`)

| 파일 | 내용 |
|------|------|
| `positions.csv` | 현재 보유 (ticker, 평가금액, asset_group) |
| `target_portfolio.csv` | 목표 포트폴리오 **템플릿** (비중 합 100%) |
| `market_indicators.csv` | 시장 지표 (KOSPI, VIX, 환율, regime 등) |
| `compass_rules.yaml` | 나침반 규칙 |
| `saa_profiles.yaml` | SAA/TAA 프로필 |
| `portfolio_policy.yaml` | 리스크 한도 |
| `trigger_rules.yaml` | 매수 트리거 |

### 5.2 Alpha 사용 시 추가

| 파일 | 내용 |
|------|------|
| `universe.csv` | KOSPI 유니버스 |
| `fundamentals.csv` | 재무 (PER, ROE, usable_from_date 등) |
| `prices.csv` | 시세·모멘텀 스냅샷 |
| `universe_filter.yaml`, `alpha_scoring.yaml` | 스크리너 설정 |

### 5.3 수동 레짐 override (선택)

`market_indicators.csv`에 아래 컬럼을 채우면 **산출 레짐 대신 수동값** 적용:

| 컬럼 | 설명 |
|------|------|
| `regime` | 예: `YELLOW_STABLE`, `RISK_ON` / `NEUTRAL`이면 산출값 사용 |
| `regime_override_reason` | 사유 (필수) |
| `regime_set_date` | 입력일 |
| `regime_expires_date` | 만료일 — **지나면 산출 레짐 자동 적용** |

Today 탭에 수동 override 안내가 표시됩니다.

---

## 6. API 키 설정

**설정** 탭 → 저장 위치: `data/local/user_secrets.json` (Git 제외)

| 키 | 용도 | 발급 |
|----|------|------|
| **DART API Key** | ROE, 부채, 현금흐름, `usable_from_date` | [Open DART](https://opendart.fss.or.kr/) |
| **KRX ID / PW** | PyKRX 일괄 수집, KOSPI 지수, 외국인 flow | [KRX 정보데이터](https://data.krx.co.kr/) |

저장 후 **DART 테스트** / **KRX 테스트** 버튼으로 연결 확인.

환경변수 `DART_API_KEY`, `KRX_ID`, `KRX_PW`도 사용 가능 (UI 저장값 우선).

---

## 7. 데이터 갱신

**데이터** 탭 또는 **검증** 탭에서 실행.

| 버튼 | 하는 일 |
|------|---------|
| **시장지표 갱신 (KOSPI+글로벌)** | KOSPI(PyKRX) + VIX·SP500·금·유가·환율(Yahoo) → `market_indicators.csv` |
| **수동 갱신** | holdings 기반 universe 병합, prices 스냅샷 |
| **PyKRX 일괄 수집** | universe + prices + fundamentals (PER/PBR) — **KRX ID/PW 필요** |
| **DART 재무 보강** | fundamentals 상세 + PIT 날짜 — **DART 키 필요** |

갱신 후 **사이드바 → 전체 분석 실행**을 다시 누르세요.

---

## 8. Alpha → Target 승인

시스템은 **절대** `target_portfolio.csv`를 자동으로 덮어쓰지 않습니다.

### 8.1 흐름

1. **Alpha** 탭 — 후보·보유 리뷰(TRIM/REPLACE) 확인  
2. **승인·Target** 탭 — 체크리스트(pass/warn/fail) 확인  
3. 변경 제안 생성 → diff 확인  
4. **반영 동의** 체크 → **승인 반영**  
5. `data/backups/`에 백업 후 `target_portfolio.csv` 갱신  

### 8.2 Data Gate가 YELLOW일 때

- Alpha gate YELLOW → **kr_alpha 신규매수**는 `trade_actions`에서 Wait 처리  
- ETF·자산군 리밸런싱 검토는 Scope `ETF_ONLY`에서 계속 가능  

---

## 9. 운용 승인 · Dry-run

### 9.1 운용승인 탭

- **운용 승인 검증 (AC)** — `acceptance_report.json` 갱신  
- **Overall / Execution Scope / Alpha Approval** 표시  
- **dry-run 누적 일수** (목표 10영업일)

### 9.2 Dry-run이란?

실제 매매 없이 **매 영업일 전체 분석만** 실행해 신호 품질을 기록하는 기간입니다.

- 로그: `outputs/dry_run_log.jsonl`  
- 스키마: [DRY_RUN_LOG_SCHEMA.md](DRY_RUN_LOG_SCHEMA.md)

GREEN 승격 전 최소 **10영업일** dry-run 권장.

---

## 10. 명령줄(CLI) 사용 (선택)

일반 운용은 **bat 더블클릭**으로 충분합니다. 아래는 고급/자동화용입니다.

| bat 파일 | CLI 동일 명령 |
|----------|----------------|
| `설치.bat` | `pip install -e ".[dev,ui,data]"` |
| `UI실행.bat` | `streamlit run app.py` |
| `실행.bat` | `python -m src.main` |
| `PyKRX일괄수집.bat` | `python -m src.data_refresh.pykrx_collect_main --scope liquid` |
| `DART재무보강.bat` | `python -m src.data_refresh.dart_collect_main --scope prices` |
| `운용승인검증.bat` | `python -m src.validation.acceptance_main` |

---

## 11. 출력 파일 안내

`outputs/` 폴더 주요 파일:

| 파일 | 용도 |
|------|------|
| `compass_regime.json` | 레짐·4축·override JSON |
| `compass_report.md` | 사람이 읽는 나침반 리포트 |
| `target_asset_allocation.csv` | 자산군 목표 % |
| `generated_target_portfolio.csv` | 자동 분해 종목 target |
| `portfolio_gap.csv` | 자산군 Gap |
| `current_vs_target.csv` | 종목 Gap |
| `trade_actions.csv` | **실행 권고** (Buy-allowed/Wait/Trim) |
| `alpha_candidates.csv` | Alpha 상위 후보 |
| `gpt_context.json` | AI·승인 체크리스트 입력 |
| `acceptance_report.json` | **운용 승인** (Overall + Scope) |
| `system_health.json` | 데이터·출력 건강 검증 |
| `dry_run_log.jsonl` | 일별 paper-run 기록 |
| `executable_brief.md` | **오늘 Executable 요약** |
| `macro_scenario.json` | 거시 3시나리오 (자동) |
| `research_checklist.json` | 리서치 10항 (자동) |
| `hakedaka_scores.csv` | 하케다카 50 추적 점수 |
| `ai_export_bundle.json` | AI 교차 검증 번들 (UI 생성) |

---

## 12. 자주 묻는 질문

### Q. "Override: manual_regime" / 수동 레짐이 뭔가요?

지표로 계산한 레짐(예: RISK_ON)과 CSV에 넣은 레짐(예: YELLOW_STABLE)이 다를 때 **수동값이 우선**됩니다. 오류가 아닙니다. 산출값을 쓰려면 `regime`을 `NEUTRAL`로 두거나 만료일을 지난 뒤 갱신하세요.

### Q. Portfolio gate GREEN인데 전체가 YELLOW인 이유?

Alpha 재무 gate가 YELLOW이면 **통합 gate**가 더 보수적으로 YELLOW가 됩니다. ETF 운용은 Scope `ETF_ONLY`로 가능, kr_alpha 신규매수만 제한됩니다.

### Q. Data Gate RED가 나왔어요

`positions.csv` / `target_portfolio.csv` 검증 실패, 또는 critical AC FAIL. **데이터**·**검증** 탭에서 원인 확인 후 수정 → 전체 분석 재실행.

### Q. 자동으로 주문되나요?

**아니요.** `trade_actions.csv`는 참고용 권고입니다. 증권사 API·자동매매는 없습니다.

### Q. target이 바뀌었는데 왜 파일이 안 바뀌나요?

의도된 설계입니다. **승인·Target** 탭에서 사람이 승인해야만 `target_portfolio.csv`가 갱신됩니다.

### Q. 처음 실운용 전에 뭘 해야 하나요?

1. API 키 설정  
2. PyKRX bulk + DART (universe 전체)  
3. 시장지표 갱신  
4. **10~20영업일 dry-run** (매일 전체 분석)  
5. 운용승인 GREEN/YELLOW + Scope 확인 후 **제한적** 적용 (ETF 우선)

---

## 13. 관련 문서

| 문서 | 대상 |
|------|------|
| [USER_GUIDE.md](USER_GUIDE.md) | **본 사용설명서** |
| [MVP_SPEC.md](MVP_SPEC.md) | 개발 스펙 (v1.0 동결) |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | 실운용 승인 기준 |
| [DRY_RUN_LOG_SCHEMA.md](DRY_RUN_LOG_SCHEMA.md) | Dry-run 기록 형식 |
| [README.md](../README.md) | 설치·빠른 시작 |

---

## 한 줄 요약

> **매일「대시보드」상태 확인 → (자동) 전체 분석 → `executable_brief`·Scope 확인 → ETF만 검토, 개별주·하케다카는 리서치, 자동매매 없음.**

문의·개선은 프로젝트 이슈 또는 `docs/` 문서를 기준으로 합니다.
