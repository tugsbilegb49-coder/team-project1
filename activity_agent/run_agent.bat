@echo off
REM Agent унавал 10 секундын дараа автоматаар дахин асаана (Өдөр 6: restart).
cd /d "%~dp0"
:loop
python agent.py run
echo Agent stopped (exit code %ERRORLEVEL%), restarting in 10 seconds... Ctrl+C to quit.
timeout /t 10 /nobreak >nul
goto loop
