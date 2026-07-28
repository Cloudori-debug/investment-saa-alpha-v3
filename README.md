# SAA 알파 투자 — v3 (활성)

**규칙 기반 실투자 보조 · Review-only.** 자동매매·증권사 API 없음.

> 코드 루트: `C:\Cursor\investment-saa-alpha-v3` · 공식 채팅: **SAA 알파 투자**  
> 배포: [`docs/V3_DEPLOY.md`](docs/V3_DEPLOY.md) · 헌장: [`docs/V3_CHARTER.md`](docs/V3_CHARTER.md)

## 빠른 시작 (이것만)

```
투자나침반.bat 더블클릭 → http://localhost:8501
→ 홈「실보유 입력」또는 사이드바「포트폴리오」
```

Go-Live 체크리스트·점검 스크립트는 **선택**(백업·업데이트 전). 필수 아님.  
선택 문서: [`docs/V3_GO_LIVE.md`](docs/V3_GO_LIVE.md)

```powershell
cd C:\Cursor\investment-saa-alpha-v3
streamlit run alpha_dashboard.py --server.address 127.0.0.1 --server.port 8501
```

설치·백업·분석 메뉴: `START_OPS_ASSISTANT.bat`  
이식: [`docs/OPS_ASSISTANT_WINDOWS_PORTABLE.md`](docs/OPS_ASSISTANT_WINDOWS_PORTABLE.md)  
패키징(Setup·업데이트): [`docs/V3_WINDOWS_PACKAGING.md`](docs/V3_WINDOWS_PACKAGING.md)

| bat / vbs | 용도 |
|-----------|------|
| **`투자나침반.bat` / `Start-Ops-Assistant.vbs`** | **일상 진입** |
| `run_ui_direct.bat` | Streamlit 직접 |
| `START_OPS_ASSISTANT.bat` | 설치 / 분석 / 백업 |
| `go_live_backup.bat` | (선택) 장부 zip |

상세: **[사용설명서](docs/USER_GUIDE.md)** · **[에이전트 시작](docs/V3_AGENT_START.md)** · **[정리(Hygiene)](docs/V3_HYGIENE.md)** · **[AGENTS.md](AGENTS.md)**

### 알파 시스템 대시보드

- ETF Executable / kr_alpha Review-only
- `target_portfolio.csv` 자동 변경 없음
- 같은 Wi-Fi 폰: `run_ui_direct.bat`는 `0.0.0.0:8501` (LAN)

## 기능 (요약)

| 모듈 | 설명 |
|------|------|
| **홈** | 오늘 할 일 · 후보·모멘텀 · 월 리밸(Review-only) |
| **포트폴리오** | 실보유 입력 · 종목별 익절 안내 |
| **확인** | CECS·목표가·주간 정성 |
| **나침반/레짐** | 레거시 멀티에셋 보조 |
- **외부 인터넷 포트 노출 금지** (LAN 전용)
- 가이드: **[ALPHA_DASHBOARD_UI_GUIDE.md](docs/ALPHA_DASHBOARD_UI_GUIDE.md)**

### (선택) 레거시 SAA 나침반 UI

```powershell
streamlit run app.py
```

CECS 알파 스크리너(하위 패키지):

```powershell
cd alpha_portfolio
pip install -e ".[data,dev]"
python -m src.main --kr-alpha-weight 31 --collect
```

## 입력 (`data/`)

| 파일 | 필수 | 설명 |
|------|------|------|
| `market_indicators.csv` | ✅ | Tier1 시장 지표 |
| `macro_tier2.csv` | ⬜ | PMI, CPI, 스프레드 등 |
| `positions.csv` | ✅ | 현재 보유 |
| `target_portfolio.csv` | ✅ | 종목 분해 **템플릿** (상대 비율) |
| `compass_rules.yaml` | ✅ | 나침반 규칙 |
| `saa_profiles.yaml` | ✅ | SAA/TAA 프로필 |
| `market_indicators_history.csv` | ⬜ | 백테스트용 |
| `portfolio_policy.yaml` | ✅ | 리스크 한도 |
| `trigger_rules.yaml` | ✅ | 매수 트리거 |

## 출력 (`outputs/`)

| 파일 | 설명 |
|------|------|
| `compass_regime.json` | v1 스키마 JSON |
| `compass_report.md` | 통합 리포트 |
| `target_asset_allocation.csv` | 자산군 목표 |
| `generated_target_portfolio.csv` | 자동 분해 종목 target |
| `portfolio_gap.csv` | 자산군 gap |
| `current_vs_target.csv` | 종목 gap |
| `trade_actions.csv` | 종목 실행 판단 |
| `exposure_lookthrough.json` | look-through 노출 진단 (region·자산·통화) |
| `final_execution_decision.json` | 최종 운용 승인 (policy_cap·technical_status) |
| `backtest_results.csv` | 백테스트 |

## SAA 프로필

| 명칭 | alias | 특징 |
|------|-------|------|
| `defensive_balanced` | `balanced` | 현금 40% + kr_alpha 31% |
| `capital_preservation` | `conservative` | 방어형 |
| `active_growth` | `growth` | 공격형 |

## 제외

- 자동매매 / 증권사 API
- 수익률 예측 / ML
- 실시간 시세 자동수집

## 문서

- **[V3 차터](docs/V3_CHARTER.md)** · **[에이전트 시작](docs/V3_AGENT_START.md)** · **[Hygiene](docs/V3_HYGIENE.md)**
- **[사용설명서](docs/USER_GUIDE.md)** — 설치·UI·일일 운용·FAQ
- **[MVP 명세서 v1.0 FROZEN](docs/MVP_SPEC.md)** — 개발 스펙 (기능 동결)
- **[운용 승인 기준](docs/ACCEPTANCE_CRITERIA.md)** — **실운용 최종 게이트**
- Dry-run 스키마: `docs/archive/20260729_hygiene/DRY_RUN_LOG_SCHEMA.md`
- `python -m src.validation.acceptance_main` — AC 검증
- 조사·RESULT·주간리포트: `docs/archive/20260729_hygiene/`

## 테스트

```powershell
# 기본 (네트워크·PyKRX 제외 — CI/일상 회귀)
pytest -m "not network and not pykrx"

# PyKRX·네트워크 스모크 (월 1회 또는 데이터 갱신 후)
pytest -m pykrx --timeout=60
pytest -m network
```

기본 스위트는 **227 passed** 기준으로 오프라인 회귀를 유지합니다. PyKRX는 별도 마커로 분리합니다.

## 릴리스

| 태그 | 내용 |
|------|------|
| `v1.0.2` / `ops-lookthrough-v1` | policy_cap + look-through 노출 레이더 |
| `v1.0.1` / `ops-stabilized` | 운용 승인 안정화 (technical vs operational) |

상세: [CHANGELOG.md](CHANGELOG.md)
