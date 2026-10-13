@echo off
setlocal
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" route --read-only --diagnostics --samples 30 --delay 5 %*
pause
endlocal
