@echo off
REM Sets SAA_PY to bundled .venv python if present, else system python/py.
REM Call with: call "%~dp0_env_python.bat"
REM Expects ROOT already set, or uses this script's parent parent (repo root).

if not defined SAA_ROOT (
  if defined ROOT (
    set "SAA_ROOT=%ROOT%"
  ) else (
    set "SAA_ROOT=%~dp0.."
  )
)
for %%I in ("%SAA_ROOT%") do set "SAA_ROOT=%%~fI"

set "SAA_PY="
if exist "%SAA_ROOT%\runtime\python\python.exe" (
  "%SAA_ROOT%\runtime\python\python.exe" -c "import streamlit" >nul 2>&1
  if not errorlevel 1 (
    set "SAA_PY=%SAA_ROOT%\runtime\python\python.exe"
    goto :eof
  )
)
if exist "%SAA_ROOT%\.venv\Scripts\python.exe" (
  "%SAA_ROOT%\.venv\Scripts\python.exe" -c "import streamlit" >nul 2>&1
  if not errorlevel 1 (
    set "SAA_PY=%SAA_ROOT%\.venv\Scripts\python.exe"
    if exist "%SAA_ROOT%\scripts\sitecustomize.venv.py" (
      copy /Y "%SAA_ROOT%\scripts\sitecustomize.venv.py" "%SAA_ROOT%\.venv\Lib\site-packages\sitecustomize.py" >nul
    )
    goto :eof
  )
)

where python >nul 2>&1
if not errorlevel 1 (
  set "SAA_PY=python"
  goto :eof
)
where py >nul 2>&1
if not errorlevel 1 (
  set "SAA_PY=py -3"
  goto :eof
)
