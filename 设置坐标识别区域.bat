@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
    echo Python environment missing. See README.md.
    pause
    exit /b 1
)
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" ocr-region %*
pause
endlocal
