# 알파 시스템 대시보드 UI — 실행 가이드

Streamlit 단일 앱. `alpha_system` 모듈을 직접 import 하며 별도 API 서버는 없습니다.

## 실행

### Windows (권장)

`투자나침반.bat` → **[1] UI 실행**

내부 명령:

```powershell
cd C:\Cursor\investment-saa-alpha
streamlit run alpha_dashboard.py --server.address 0.0.0.0
```

### 터미널

```powershell
pip install -e ".[dev,ui,data]"
streamlit run alpha_dashboard.py --server.address 0.0.0.0
```

## 폰 접속 (같은 Wi-Fi)

1. PC와 폰이 **동일 Wi-Fi**에 연결되어 있는지 확인합니다.
2. PC의 로컬 IP를 확인합니다 (`ipconfig` → IPv4, 예: `192.168.0.12`).
3. 폰 브라우저에서 `http://192.168.0.12:8501` 로 접속합니다.

### 보안 경고

- **`0.0.0.0` 바인딩은 LAN 공유용**입니다. 라우터 포트포워딩·DMZ로 **외부 인터넷에 노출하지 마세요**.
- 대시보드는 읽기 전용이 우선이나, 저널·T2/논지훼손 입력은 운용 기록을 남깁니다.
- 공용 네트워크에서는 실행하지 않습니다.

## 화면 구성

| 화면 | 파일 | 설명 |
|------|------|------|
| 홈 | `alpha_system/ui/pages/home.py` | 액션 큐, 트랜치 4칸, window_end, 지표, 데이터 상태 |
| 설정·이벤트 | `alpha_system/ui/pages/settings.py` | config 조회, T2/논지훼손, 데이터 갱신 |
| 포트폴리오 | `alpha_system/ui/pages/portfolio.py` | kr_alpha 종목 상세 |
| 스코어 | `alpha_system/ui/pages/scores.py` | CECS 30종 테이블 |
| 저널 | `alpha_system/ui/pages/journal.py` | 타임라인 + 재량/목표가 기입 |

진입점: [`alpha_dashboard.py`](../alpha_dashboard.py)

## 데이터 갱신

- **설정·이벤트 → 데이터 갱신** 버튼은 **앱이 실행 중인 PC**에서 PyKRX 일괄 수집을 호출합니다.
- 권장 주기는 [`alpha_system/config/dashboard.yaml`](../alpha_system/config/dashboard.yaml) 에 정의되어 있습니다.
- T3(KOSPI 시장 PBR 10년 하위 20%)는 **월 1회** 판정용 이력 CSV가 필요합니다.
  - 경로: `data/kospi_market_pbr_history.csv` (`month_end`, `market_pbr`)
  - PyKRX `get_index_fundamental` 단일 스냅샷만으로는 10년 백분위를 산출할 수 없습니다.

## 폰 점검 체크리스트

| # | 항목 | 기준 |
|---|------|------|
| ① | 액션 큐 | 홈 첫 화면 스크롤 없이 보임 |
| ② | 스코어 테이블 | 종목명·total·eligibility·보유 4열이 가독 가능 |
| ③ | 재량 기록 | 저널 화면에서 한 손으로 종목·사유·저장 가능 |
| ④ | T2 2단계 확인 | 경고 2체크박스 + 최종 버튼 없이는 저장 불가 |

## 스크린샷 (폰 비율)

운용자가 가동 확인 시 아래 5장을 이 문서와 같은 폴더에 추가합니다.

| 파일 | 화면 |
|------|------|
| `docs/screenshots/alpha_dashboard_home_mobile.png` | 홈 |
| `docs/screenshots/alpha_dashboard_settings_mobile.png` | 설정·이벤트 |
| `docs/screenshots/alpha_dashboard_portfolio_mobile.png` | 포트폴리오 |
| `docs/screenshots/alpha_dashboard_scores_mobile.png` | 스코어 |
| `docs/screenshots/alpha_dashboard_journal_mobile.png` | 저널 |

*(스크린샷은 실제 폰 촬영 후 교체)*

## 레거시 UI

기존 SAA 나침반 콘솔은 [`app.py`](../app.py) 에 그대로 있습니다. 알파 단독 운용 대시보드는 `alpha_dashboard.py` 를 사용합니다.
