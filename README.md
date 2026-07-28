# Multi-Asset Trigger Portfolio v2.0

**규칙 기반 자산군 나침반 + SAA/TAA + 종목 분해 + 실행 보조 + 백테스트**

> 자동매매·증권사 API 없음. 일관된 배분 의사결정 자동화가 목표입니다.

## 기능

| 모듈 | 설명 |
|------|------|
| **나침반** | Tier1 시장지표 + Tier2 매크로 → 레짐·시장국면·4축 점수 |
| **SAA/TAA** | 프로필별 자산군 목표비중 (`target_asset_allocation.csv`) |
| **종목 분해** | 자산군 비중 → `generated_target_portfolio.csv` |
| **자산군 Gap** | `portfolio_gap.csv` — Buy/Hold/Trim/Park/NoTrade |
| **종목 실행** | 트리거 기반 Buy/Wait/Trim (`trade_actions.csv`) |
| **백테스트** | 히스토리 CSV로 레짐·배분 전환 검증 |
| **Streamlit UI** | SAA 운용 콘솔 (`app.py`) · **알파 시스템 대시보드** (`alpha_dashboard.py`) |

## 빠른 시작 (일상)

```
1. Start-Ops-Assistant.vbs   ← 더블클릭 (CMD 최소화 · 브라우저 전면)
2. 또는 투자나침반.bat       ← 동일 (VBS 호출)
```

설치·백업·분석 메뉴: `START_OPS_ASSISTANT.bat`  
이식 가이드: [`docs/OPS_ASSISTANT_WINDOWS_PORTABLE.md`](docs/OPS_ASSISTANT_WINDOWS_PORTABLE.md)

### (레거시) 메뉴형 진입

```
투자나침반.bat → Start-Ops-Assistant.vbs
```

| bat / vbs | 용도 |
|-----------|------|
| **`Start-Ops-Assistant.vbs`** | **일상 진입 (권장)** — UI 바로 |
| `START_OPS_ASSISTANT.bat` | 설치 / 분석 / 백업 / UI |
| `run_ui_direct.bat` | VBS가 호출하는 직접 UI |
| `투자나침반.bat` | VBS 래퍼 (ASCII) |

상세: **[사용설명서](docs/USER_GUIDE.md)** · 채팅 승계: **[레거시 핸드오프](docs/CHAT_HANDOFF_LEGACY_MULTI_ASSET.md)** · **[AGENTS.md](AGENTS.md)**

### 알파 시스템 대시보드 (모바일 우선)

```powershell
streamlit run alpha_dashboard.py --server.address 0.0.0.0
```

- 같은 Wi-Fi 폰: `http://<PC-IP>:8501`
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

- **[사용설명서](docs/USER_GUIDE.md)** — 설치·UI·일일 운용·FAQ
- **[MVP 명세서 v1.0 FROZEN](docs/MVP_SPEC.md)** — 개발 스펙 (기능 동결)
- **[운용 승인 기준](docs/ACCEPTANCE_CRITERIA.md)** — **실운용 최종 게이트**
- **[Dry-run 스키마](docs/DRY_RUN_LOG_SCHEMA.md)** — paper-run 기록
- `python -m src.validation.acceptance_main` — AC 검증

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
