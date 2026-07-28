@echo off
REM Direct UI start - no menu. Called by Start-Ops-Assistant.vbs (minimized).
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
title SAA Alpha Ops Assistant UI
cd /d "%~dp0"

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.11+ with PATH.
  pause
  exit /b 1
)

%PY% -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo Installing packages first time...
  %PY% -m pip install --upgrade pip
  %PY% -m pip install -e ".[dev,ui,data]"
  if errorlevel 1 (
    echo [ERROR] Install failed.
    pause
    exit /b 1
  )
)

echo [SAA] UI starting - http://localhost:8501
echo [SAA] Keep this window open. Close it to stop the app.
echo.
%PY% -m streamlit run "%~dp0alpha_dashboard.py" --server.address 0.0.0.0 --server.headless false --browser.gatherUsageStats false
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] UI exited with code %EC%
  pause
)
exit /b %EC%
