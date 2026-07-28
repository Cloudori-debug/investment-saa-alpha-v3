@echo off
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
title SAA Alpha Ops Assistant
cd /d "%~dp0"

echo.
echo [SAA] Launcher starting...
echo [SAA] Folder: %CD%
echo.
echo   Daily use: double-click  Start-Ops-Assistant.vbs
echo   (UI opens, CMD stays minimized)
echo.

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo [ERROR] Python not found.
  echo Install Python 3.11+ and check "Add python.exe to PATH".
  echo https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo [SAA] Python: %PY%
%PY% --version
if errorlevel 1 (
  echo [ERROR] Python failed to start.
  echo Tip: Settings - Apps - Advanced app settings - App execution aliases
  echo      Turn OFF python.exe / python3.exe aliases.
  pause
  exit /b 1
)
echo.

:MENU
echo ================================================
echo   SAA Alpha Ops Assistant
echo   %CD%
echo   (personal ops assistant - not auto-trading)
echo ================================================
echo.
echo   Checking API status...
%PY% "%~dp0scripts\launcher_cred_status.py"
if errorlevel 1 echo   API: unavailable
echo.
echo [1] UI now (this window)
echo [2] Install
echo [3] Analysis
echo [4] Backup zip (format / other PC)
echo [5] UI minimized (same as .vbs)
echo [0] Exit
echo.
set "SEL="
set /p SEL=Select 1/2/3/4/5/0 then Enter: 
if "%SEL%"=="1" goto RUN_UI
if "%SEL%"=="2" goto RUN_INSTALL
if "%SEL%"=="3" goto RUN_ANALYSIS
if "%SEL%"=="4" goto RUN_BACKUP
if "%SEL%"=="5" goto RUN_UI_MIN
if "%SEL%"=="0" goto EXIT
echo.
echo [WARN] Unknown input: "%SEL%"
echo.
goto MENU

:RUN_BACKUP
echo.
echo Creating ops assistant backup zip...
%PY% "%~dp0scripts\make_ops_backup.py" --root "%~dp0."
if errorlevel 1 goto FAIL
echo.
echo Copy zip from data\local\backups\ before format.
echo.
pause
goto MENU

:RUN_UI_MIN
echo.
echo Starting minimized UI via VBS...
wscript //nologo "%~dp0Start-Ops-Assistant.vbs"
echo Browser should open at http://localhost:8501
echo To stop: restore the minimized console and press Ctrl+C, or close it.
echo.
pause
goto MENU

:RUN_UI
echo.
%PY% -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo streamlit missing - installing packages...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -e ".[dev,ui,data]"
    if errorlevel 1 goto FAIL
)
echo Starting UI...
echo   File: %CD%\alpha_dashboard.py
echo   Browser: http://localhost:8501
echo   Stop: Ctrl+C
echo.
%PY% -m streamlit run "%~dp0alpha_dashboard.py" --server.address 0.0.0.0 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 goto FAIL
echo.
echo UI stopped.
pause
goto MENU

:RUN_INSTALL
echo.
echo Installing packages...
%PY% -m pip install --upgrade pip
%PY% -m pip install -e ".[dev,ui,data]"
if errorlevel 1 goto FAIL
echo.
echo Install done.
pause
goto MENU

:RUN_ANALYSIS
echo.
echo Running analysis --refresh-market ...
%PY% -m src.main --refresh-market
if errorlevel 1 goto FAIL
echo.
pause
goto MENU

:FAIL
echo.
echo [ERROR] Failed. Read messages above.
pause
goto MENU

:EXIT
echo Bye.
endlocal
exit /b 0
