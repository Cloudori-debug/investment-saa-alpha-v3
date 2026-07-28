@echo off
REM ASCII-only daily entry -> Start-Ops-Assistant.vbs
cd /d "%~dp0"
if not exist "%~dp0Start-Ops-Assistant.vbs" (
  echo [ERROR] Start-Ops-Assistant.vbs missing.
  pause
  exit /b 1
)
wscript //nologo "%~dp0Start-Ops-Assistant.vbs"
