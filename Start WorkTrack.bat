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

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" worktrack.py %ARGS%
  goto done
)
rem First run: any Python 3.10+ creates .venv; the py launcher is preferred over the Store alias.
py -3 --version >nul 2>nul
if not errorlevel 1 (
  py -3 worktrack.py %ARGS%
  goto done
)
python --version >nul 2>nul
if not errorlevel 1 (
  python worktrack.py %ARGS%
  goto done
)
echo.
echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then open this file again.
echo.
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
