@echo off
setlocal
cd /d "%~dp0"
echo Read-only minimap capture for 10 seconds. NO keyboard or mouse input.
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" scan-sequence --capture --delay 5 --seconds 10
pause
endlocal
