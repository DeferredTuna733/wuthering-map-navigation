@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo One short W step: no mouse correction.
choice /C YN /N /M "Start? Press Y to continue, N to cancel: "
if errorlevel 2 exit /b 0
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" temporal-step --execute --delay 15 --seconds 0.35
set RESULT=%errorlevel%
echo Exit code %RESULT%.
pause
endlocal
exit /b %RESULT%
