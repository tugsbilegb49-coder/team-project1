@echo off
rem Double-click to start WorkTrack on Windows (same as Start WorkTrack.command on macOS).
rem Default is desktop mode: the web page controls the agent and camera.
rem Other modes: "Start WorkTrack.bat" --web-only  (or --camera, --desktop, --no-browser)
setlocal
cd /d "%~dp0"
title WorkTrack
chcp 65001 >nul
set PYTHONUTF8=1
if "%~1"=="" (set "ARGS=--desktop") else (set "ARGS=%*")

rem Prefer the project's own Python, then the py launcher, then python on PATH.
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  py -3 --version >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
set "NEED_PYTHON="
set "NEED_NODE="
if not defined PY set "NEED_PYTHON=1"
where node >nul 2>nul || set "NEED_NODE=1"
if defined NEED_PYTHON goto install
if defined NEED_NODE goto install

%PY% worktrack.py %ARGS%
goto done

:install
echo.
echo WorkTrack needs these free programs first:
if defined NEED_PYTHON echo   - Python 3.12
if defined NEED_NODE echo   - Node.js LTS
echo.
where winget >nul 2>nul
if errorlevel 1 goto manual
choice /c YN /m "Install them now (Windows may ask for permission)"
if errorlevel 2 goto manual
if defined NEED_PYTHON winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if defined NEED_NODE winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
echo.
echo Done. Close this window and open Start WorkTrack.bat again.
pause
exit /b 0

:manual
if defined NEED_PYTHON (
  echo Python: https://www.python.org/downloads/  - tick "Add python.exe to PATH" while installing.
  start "" https://www.python.org/downloads/
)
if defined NEED_NODE (
  echo Node.js: https://nodejs.org/  - choose the LTS version.
  start "" https://nodejs.org/
)
echo.
echo The download pages are open in your browser. Install, then open Start WorkTrack.bat again.
pause
exit /b 1

:done
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" (
  echo.
  echo WorkTrack stopped with an error ^(see the message above and the .runtime folder^).
  pause
)
exit /b %RESULT%
