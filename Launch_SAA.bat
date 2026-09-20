@echo off
REM ASCII shortcut / Setup icon - same as daily launcher
cd /d "%~dp0"
if exist "%~dp0Start-Ops-Assistant.vbs" (
  start "" wscript //nologo "%~dp0Start-Ops-Assistant.vbs"
  exit /b 0
)
echo [ERROR] Start-Ops-Assistant.vbs missing.
pause
exit /b 1
