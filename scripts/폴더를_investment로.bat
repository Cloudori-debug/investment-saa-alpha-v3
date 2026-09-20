@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 두 프로그램을 investment 아래로

echo.
echo   Cursor 와 알파·수급 창을 모두 닫은 뒤 이 파일을 실행하세요.
echo   열려 있으면 "다른 프로세스가 사용 중" 으로 실패합니다.
echo.
pause

set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"
for %%I in ("%HERE%\..") do set "SRC_ALPHA=%%~fI"
set "PARENT=%SRC_ALPHA%\.."
for %%I in ("%PARENT%") do set "PARENT=%%~fI"

set "DEST_ROOT=%PARENT%\investment"
set "DEST_ALPHA=%DEST_ROOT%\investment-alpha-screener"
set "DEST_FUND=%DEST_ROOT%\investment-fund-screener"
set "SRC_FUND=%PARENT%\investment-site"
if exist "%PARENT%\investment\investment-fund-screener\수급브리핑.bat" (
  set "SRC_FUND=%PARENT%\investment\investment-fund-screener"
)

echo   목적지: %DEST_ROOT%
echo.

if /I "%SRC_ALPHA%"=="%DEST_ALPHA%" (
  echo   알파는 이미 옮겨져 있습니다.
  goto FUND
)

mkdir "%DEST_ROOT%" 2>nul
if exist "%DEST_ALPHA%" (
  echo   [오류] 이미 있습니다: %DEST_ALPHA%
  pause
  exit /b 1
)

echo   알파 이동 중...
move "%SRC_ALPHA%" "%DEST_ALPHA%"
if errorlevel 1 (
  echo   [오류] 알파 폴더를 옮기지 못했습니다. Cursor를 종료한 뒤 다시 시도하세요.
  pause
  exit /b 1
)
echo   알파 → %DEST_ALPHA%

:FUND
if exist "%DEST_FUND%\수급브리핑.bat" (
  echo   수급은 이미 있습니다: %DEST_FUND%
  goto DONE
)
if not exist "%SRC_FUND%\수급브리핑.bat" if not exist "%SRC_FUND%\start.bat" (
  echo   [안내] 수급 폴더를 못 찾았습니다. 알파만 옮겼습니다.
  echo           기대 경로: %PARENT%\investment-site
  goto DONE
)
if exist "%DEST_FUND%" (
  echo   [오류] 이미 있습니다: %DEST_FUND%
  pause
  exit /b 1
)
echo   수급 이동 중...
move "%SRC_FUND%" "%DEST_FUND%"
if errorlevel 1 (
  echo   [오류] 수급 폴더를 옮기지 못했습니다.
  pause
  exit /b 1
)
echo   수급 → %DEST_FUND%

:DONE
(
echo # investment
echo.
echo 두 프로그램은 형제 폴더입니다. 점수·장부·venv를 합치지 마세요.
echo.
echo - investment-alpha-screener : 알파 스크리너. 투자나침반.bat
echo - investment-fund-screener : 수급 브리핑. 수급브리핑.bat
echo.
echo 다른 PC: 설정 도구에서 이사 준비. .venv 는 새 PC에서 다시 만들어집니다. data 와 .env 는 꼭 같이 복사하세요.
) > "%DEST_ROOT%\README.md"
echo.
echo   완료. Cursor에서 폴더를 다시 여세요:
echo     %DEST_ROOT%\investment-alpha-screener
echo   수급: %DEST_ROOT%\investment-fund-screener
echo   두 프로그램은 합치지 않습니다.
echo.
if exist "%DEST_ROOT%" explorer "%DEST_ROOT%"
pause
exit /b 0
