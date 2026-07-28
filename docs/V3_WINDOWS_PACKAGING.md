# v3 Windows 패키징 — 설치 · 업데이트 · 사용

> **제품:** 개인 운용 비서 (자동매매 아님)  
> **코드 루트:** `C:\Cursor\investment-saa-alpha-v3`

---

## 한 줄

| 역할 | 파일 |
|------|------|
| 매일 실행 | `투자나침반.bat` |
| 메뉴(설치·백업·업데이트) | `START_OPS_ASSISTANT.bat` |
| 장부 유지 업데이트 | `업데이트.bat` + `saa-alpha-update.zip` |
| 포터블 빌드 | `scripts\bundle_runtime.ps1` |
| 설치기(Setup.exe) | `packaging\saa_alpha.iss` (Inno Setup) |

런처는 **`.venv\Scripts\python.exe`가 있으면 그걸 우선** 사용합니다. 없으면 시스템 Python.

---

## A. 개발 PC에서 포터블 만들기

```powershell
cd C:\Cursor\investment-saa-alpha-v3
powershell -ExecutionPolicy Bypass -File scripts\bundle_runtime.ps1 -Zip
```

결과:

- `dist\SAA-Alpha-portable\` — 폴더 통째 복사해도 동작(내장 venv)
- `dist\SAA-Alpha-portable-YYYYMMDD.zip` — (`-Zip` 시)

이 zip을 다른 PC에 풀어 `투자나침반.bat`만 실행하면 됩니다(시스템 Python 불필요).

---

## B. Setup.exe (Inno Setup)

1. [Inno Setup](https://jrsoftware.org/isinfo.php) 설치  
2. `bundle_runtime.ps1` 으로 `dist\SAA-Alpha-portable` 생성  
3. `packaging\saa_alpha.iss` 열어 **Compile**  
4. 산출: `packaging\Output\SAAAlphaSetup-3.0.1.exe`

설치 기본 경로: `%LOCALAPPDATA%\SAA-Alpha` (관리자 권한 불필요)  
업그레이드 시 `data\` 는 **onlyifdoesntexist** — 기존 장부 유지.

---

## C. 사용 중 업데이트 (장부 보존)

1. 새 포터블 zip을 `saa-alpha-update.zip` 으로 설치 폴더에 두거나  
2. `업데이트.bat` 실행 (또는 `업데이트.bat D:\path\update.zip`)  
3. UI를 끄고 다시 `투자나침반.bat`

동작 요약 (`scripts\apply_update.ps1`):

- 업데이트 전 `data\local\backups\pre_update_*` 에 핵심 장부 스냅샷  
- **`data\` 디렉터리 전체를 덮어쓰지 않음**  
- 없는 seed 파일만 data에 추가  
- (선택) `-AlsoRefreshVenv` 로 런타임 교체

---

## D. 장부 백업 (포맷·이사)

기존과 동일: 메뉴 `[4] Backup` / 설정 › 이식·백업 / `docs\OPS_ASSISTANT_WINDOWS_PORTABLE.md`

---

## 범위

| 포함 | 미포함 |
|------|--------|
| 포터블 zip · Setup.exe 초안 · data 보존 업데이트 | 앱스토어 · 단일 exe(PyInstaller) · 자동매매 |
| 시작메뉴·바로가기 | Mac/Linux 패키지 |

---

## 불변

- `proposal_mode: pure_qvm` · `target_portfolio.csv` 사람만  
- Review-only (kr_alpha) · FASTJUSIK 금지
