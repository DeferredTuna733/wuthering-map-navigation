@echo off
setlocal
cd /d "%~dp0"
echo Temporal direction reference check. NO keyboard or mouse input.
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" temporal-step --read-only --delay 5
pause
endlocal
