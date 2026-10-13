@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\pythonw.exe" (
    echo Python environment missing. Please see README.md.
    pause
    exit /b 1
)
start "" "%~dp0venv\Scripts\pythonw.exe" -B "%~dp0run.py" map
endlocal
