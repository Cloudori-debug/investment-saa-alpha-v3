@echo off
REM Direct UI start - prefers bundled .venv (packaged install).
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
title SAA Alpha Ops Assistant UI
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

call "%~dp0scripts\_env_python.bat"
if not defined SAA_PY (
  echo [ERROR] Python not found.
  echo Install Python 3.11+ with PATH, or run packaging\bundle first.
  echo See docs\V3_WINDOWS_PACKAGING.md
  pause
  exit /b 1
)
set "PY=%SAA_PY%"
echo [SAA] Python: %PY%

%PY% -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo Installing packages first time...
  %PY% -m pip install --upgrade pip
  %PY% -m pip install -e ".[ui,data]"
  if errorlevel 1 (
    echo [ERROR] Install failed.
    pause
    exit /b 1
  )
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
