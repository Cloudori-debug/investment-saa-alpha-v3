@echo off
REM Direct UI start - prefers bundled .venv (packaged install).
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
title KOSPI Alpha Screener UI [v3]
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo [SAA] root=%ROOT%
if not exist "%ROOT%\alpha_dashboard.py" (
  echo [ERROR] alpha_dashboard.py missing. Copy the whole program folder.
  pause
  exit /b 1
)

call "%~dp0scripts\_env_python.bat"
if not defined SAA_PY (
  echo [ERROR] Python not found.
  echo Install Python 3.11+ with PATH, then run the daily launcher again.
  echo https://www.python.org/downloads/
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

echo [SAA] UI starting - http://localhost:8501
echo [SAA] Keep this window open. Close it to stop the app.
echo.
REM headless true: browser is opened once by Start-Ops-Assistant.vbs (avoid double tabs)
%PY% -m streamlit run "%~dp0alpha_dashboard.py" --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] UI exited with code %EC%
  pause
)
exit /b %EC%
