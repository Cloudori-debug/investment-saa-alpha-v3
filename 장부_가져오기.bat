@echo off
REM Import ledger from folder or zip (carry kit half #2)
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

set "SRC=%~1"
if "%SRC%"=="" (
  if exist "%~dp0dist\CARRY\02_SAA-Alpha-Backup\README_BACKUP.txt" (
    set "SRC=%~dp0dist\CARRY\02_SAA-Alpha-Backup"
  )
)
if "%SRC%"=="" (
  echo.
  echo 사용법: 장부_가져오기.bat  백업폴더경로
  echo    또는: 장부_가져오기.bat  backup.zip
  echo.
  echo 예: 장부_가져오기.bat D:\USB\02_SAA-Alpha-Backup
  echo.
  set /p SRC=백업 폴더 또는 zip 경로 입력: 
)
if "%SRC%"=="" (
  echo 취소됨.
  pause
  exit /b 1
)

echo.
echo [SAA] 장부 가져오기 — 프로그램은 그대로, 장부만 덮어씁니다.
echo [SAA] from: %SRC%
echo.
"%SAA_PY%" "%~dp0scripts\import_ledger.py" --root "%ROOT%" "%SRC%"
if errorlevel 1 (
  echo [ERROR] import failed
  pause
  exit /b 1
)
echo.
echo 완료. 투자나침반.bat 으로 다시 여세요.
pause
exit /b 0
