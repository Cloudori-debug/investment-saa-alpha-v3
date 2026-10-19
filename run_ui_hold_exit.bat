@echo off
REM Hold/Exit Review edition UI - port 8502. Does not replace 8501.
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
title Alpha Screener Hold-Exit Review [v3]
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo [SAA] Hold-Exit edition root=%ROOT%
if not exist "%ROOT%\alpha_dashboard_hold_exit.py" (
  echo [ERROR] alpha_dashboard_hold_exit.py missing.
  pause
  exit /b 1
)

call "%~dp0scripts\_env_python.bat"
if not defined SAA_PY (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)
set "PY=%SAA_PY%"
echo [SAA] Python: %PY%

echo [SAA] checking local runtime...
%PY% "%ROOT%\scripts\ensure_runtime.py" --root "%ROOT%"
if errorlevel 1 (
  echo [ERROR] Could not create/repair .venv
  pause
  exit /b 1
)
call "%~dp0scripts\_env_python.bat"
set "PY=%SAA_PY%"
if not defined PY (
  echo [ERROR] Python missing after runtime repair.
  pause
  exit /b 1
)

echo [SAA] UI starting - http://127.0.0.1:8502
echo [SAA] Keep this window open. Close it to stop the app.
echo.
%PY% -m streamlit run "%~dp0alpha_dashboard_hold_exit.py" --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] Hold-Exit UI exited with code %EC%
  pause
)
exit /b %EC%
