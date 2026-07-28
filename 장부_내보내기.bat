@echo off
REM Export ledger -> dist\CARRY\02_SAA-Alpha-Backup  (carry kit half #2)
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
call "%~dp0scripts\_env_python.bat"
if not defined SAA_PY (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)
echo.
echo [SAA] 장부 내보내기 — 프로그램과 따로 들고 다닐 백업 폴더를 만듭니다.
echo.
"%SAA_PY%" "%~dp0scripts\export_ledger.py" --root "%ROOT%"
if errorlevel 1 (
  echo [ERROR] export failed
  pause
  exit /b 1
)
echo.
echo 폴더: %ROOT%\dist\CARRY\02_SAA-Alpha-Backup
echo USB/클라우드에 이 폴더만 복사하면 됩니다.
explorer "%ROOT%\dist\CARRY\02_SAA-Alpha-Backup"
pause
exit /b 0
