# v3 Windows 패키징 — 다른 PC에 설치

> **제품:** 알파 스크리너 (자동매매 아님)  
> **코드 루트:** `C:\Cursor\investment\investment-alpha-screener`

---

## 한 줄

다른 PC에는 **폴더(또는 zip)** 를 복사합니다. 미서명 Setup.exe는 쓰지 않습니다(SmartScreen).  
패키지에 **API 키·실보유·가동 런타임은 넣지 않습니다.**

| 역할 | 파일 |
|------|------|
| 이 PC에서 패키지 만들기 | `python scripts/pack_portable.py --zip` |
| 다른 PC에서 실행 | `투자나침반.bat` 또는 `Launch_SAA.bat` |
| 시작 메뉴에 넣기 | `install.bat` |
| 매일 실행 | `투자나침반.bat` |

다른 PC에 **Python을 따로 설치하지 않습니다.** 공식 embed Python(`runtime\python\python.exe`, PSF 서명)이 들어갑니다.

---

## A. 이 PC에서 만들기

```powershell
cd C:\Cursor\investment\investment-alpha-screener
python scripts/pack_portable.py --zip
```

결과:

- `dist\AlphaScreener-portable\` — 폴더 통째 USB 복사
- `dist\AlphaScreener-portable.zip` — (`--zip` 시)

들어가지 않는 것: `data/local/user_secrets.json`, `.env`, `positions.csv`, `alpha_dashboard_runtime.json`, `.venv`, `.git`.

---

## B. 다른 PC

1. zip이면 속성 → **차단 해제** 후 압축 해제 (인터넷에서 받은 경우). USB로 복사하면 이 단계가 없습니다.
2. `install.bat` → `%LOCALAPPDATA%\AlphaScreener` 복사 + 시작 메뉴 `Alpha Screener`
3. 또는 폴더에서 `Launch_SAA.bat` / `투자나침반.bat`만 실행
4. 설정에서 DART·KRX 키를 **그 PC에만** 입력
5. 확인 › ③ 가동 한 번 선언 → ① 정량 갱신

Inno Setup / `SAAAlphaSetup.exe`는 선택이며, 미서명이라 Smart App Control에 걸릴 수 있습니다. 기본 경로는 위 폴더 복사입니다.

---

## 불변

- `proposal_mode: pure_qvm` · `target_portfolio.csv` 사람만  
- Review-only · FASTJUSIK 금지
