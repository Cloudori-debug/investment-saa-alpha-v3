@echo off
REM ASCII-only daily entry -> Start-Ops-Assistant.vbs
REM start = do not block this CMD while VBS waits for Streamlit
cd /d "%~dp0"
if not exist "%~dp0Start-Ops-Assistant.vbs" (
  echo [ERROR] Start-Ops-Assistant.vbs missing.
  pause
  exit /b 1
)
start "" wscript //nologo "%~dp0Start-Ops-Assistant.vbs"
exit /b 0
