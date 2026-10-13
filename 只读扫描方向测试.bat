@echo off
setlocal
cd /d "%~dp0"
echo Read-only minimap sample. NO keyboard or mouse input.
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" heading-step --read-only --game-process Client-Win64-Shipping.exe --delay 5
set RESULT=%errorlevel%
echo Exit code %RESULT%.
pause
endlocal
exit /b %RESULT%
