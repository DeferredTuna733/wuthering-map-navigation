@echo off
setlocal
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" minimap-region %*
pause
endlocal
