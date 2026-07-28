@echo off
REM ASCII launcher for shortcuts / Setup icons (calls VBS daily entry)
cd /d "%~dp0"
if exist "%~dp0Start-Ops-Assistant.vbs" (
  wscript //nologo "%~dp0Start-Ops-Assistant.vbs"
  exit /b 0
)
if exist "%~dp0run_ui_direct.bat" (
  call "%~dp0run_ui_direct.bat"
  exit /b %ERRORLEVEL%
)
echo [ERROR] Start-Ops-Assistant.vbs missing.
pause
exit /b 1
