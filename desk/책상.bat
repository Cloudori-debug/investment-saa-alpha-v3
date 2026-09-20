@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 책상
cd /d "%~dp0"

set "DESK=%~dp0"
set "DESK=%DESK:~0,-1%"
set "ALPHA=%DESK%\.."
for %%I in ("%ALPHA%") do set "ALPHA=%%~fI"
set "FLOW=%ALPHA%\..\investment-fund-screener"
if not exist "%FLOW%\수급브리핑.bat" if not exist "%FLOW%\start.bat" (
  set "FLOW=%ALPHA%\..\investment-site"
)
for %%I in ("%FLOW%") do set "FLOW=%%~fI"

echo.
echo   책상 — 두 프로그램은 따로 켜집니다. 점수·장부는 섞지 않습니다.
echo.

if exist "%ALPHA%\run_ui_direct.bat" (
  echo   알파 스크리너 시작...
  start "Alpha Screener" /min cmd /c call "%ALPHA%\run_ui_direct.bat"
) else (
  echo   [경고] 알파 런처를 못 찾았습니다: %ALPHA%
)

if exist "%FLOW%\수급브리핑.bat" (
  echo   수급 브리핑 시작...
  start "수급 브리핑" /min cmd /c call "%FLOW%\수급브리핑.bat"
) else if exist "%FLOW%\start.bat" (
  echo   수급 브리핑 시작...
  start "수급 브리핑" /min cmd /c call "%FLOW%\start.bat"
) else (
  echo   [안내] 수급 폴더가 옆에 없습니다. 알파만 켭니다.
  echo           기대 경로: %FLOW%
)

echo   알파(8501)가 켜질 때까지 기다립니다...
set "ALPHA_UP="
for /L %%i in (1,1,45) do (
  netstat -ano | findstr /C:"LISTENING" | findstr /C:":8501" >nul 2>&1
  if not errorlevel 1 (
    set "ALPHA_UP=1"
    goto :open_desk
  )
  timeout /t 2 /nobreak >nul
)

:open_desk
if not defined ALPHA_UP (
  echo   [안내] 90초 안에 알파가 안 켜졌습니다. 최소화된 'KOSPI Alpha Screener UI' 창을 확인하세요.
)
echo   책상 페이지를 엽니다.
start "" "%DESK%\책상.html"
if defined ALPHA_UP start "" "http://127.0.0.1:8501"
echo.
echo   이 창은 닫아도 됩니다. 각 프로그램 창은 닫지 마세요.
timeout /t 3 >nul
exit /b 0
