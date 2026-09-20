# 책상 포털 — 수급과 나란히, 시스템은 섞지 않음

> **결론:** 한 폴더에서 **실행만** 묶는 것은 안전하다. 한 앱·한 데이터·한 점수로 합치는 것은 안전하지 않다.

## 두 프로그램

| | 알파 스크리너 | 수급 브리핑 |
|--|----------------------|---------------------------|
| 폴더 | `C:\Cursor\investment\investment-alpha-screener` | `C:\Cursor\investment\investment-fund-screener` |
| 엔진 | Streamlit · QVM 순위 · `data/` CSV | FastAPI · `pension.db` · 연기금 연속 순매수 |
| 포트 | `127.0.0.1:8501` | `127.0.0.1:8000` |
| 일상 실행 | `투자나침반.bat` | `수급브리핑.bat` |

차터: **kr_alpha·하케다카·수급 = Review-only**. 수급 선정 종목이 알파 `total_score`나 `target_portfolio.csv`에 들어가면 안 된다.

## 해도 되는 것

- 형제 폴더를 그대로 두고, `desk/책상.bat`이 **각자 프로세스**를 켠다.
- `desk/책상.html`이 두 URL만 연다. Python import·공유 DB 없음.
- 화면 색·글꼴만 맞춘다 (이미 수급 브리핑의 종이·잉크 토큰을 알파 UI에 복사).

## 하면 안 되는 것

- 한 Streamlit 앱에 수급 페이지를 붙이기
- `.venv` / `data/` / `pension.db` 공유
- 연기금 강도를 QVM 순위에 가산
- 한 프로세스가 두 장부를 쓰기

예전 합의와 같다: 필요하면 수급에서 고른 종목을 알파에 **눈으로만** 참고한다. 매수 순위는 불변.

## 쓰는 법

`desk/책상.bat` 더블클릭. 수급 폴더가 옆에 없으면 알파만 켜고 HTML에 안내가 뜬다.
