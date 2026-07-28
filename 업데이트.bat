@echo off
REM Apply update zip while preserving data\
setlocal EnableExtensions
cd /d "%~dp0"

set "ZIP=%~1"
if "%ZIP%"=="" (
  if exist "%~dp0saa-alpha-update.zip" set "ZIP=%~dp0saa-alpha-update.zip"
)

echo.
echo [SAA] Update — data\ 장부는 유지합니다.
echo [SAA] Folder: %CD%
if not "%ZIP%"=="" echo [SAA] Zip: %ZIP%
echo.

if "%ZIP%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\apply_update.ps1" -InstallRoot "%~dp0."
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\apply_update.ps1" -InstallRoot "%~dp0." -ZipPath "%ZIP%"
)
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] Update failed. Check messages above.
  echo Tip: 업데이트.bat path\to\saa-alpha-update.zip
  pause
  exit /b %EC%
)
echo.
echo Done. Close UI if open, then run 투자나침반.bat
pause
exit /b 0
