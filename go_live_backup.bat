@echo off
REM Personal go-live ledger backup (no secrets by default)
cd /d "%~dp0"
echo [SAA] Creating ops backup zip...
python scripts\make_ops_backup.py
if errorlevel 1 (
  echo [ERROR] Backup failed.
  pause
  exit /b 1
)
echo.
echo [SAA] Copy the zip under data\local\backups\ to USB or encrypted cloud.
echo [SAA] Checklist: docs\V3_GO_LIVE.md
pause
