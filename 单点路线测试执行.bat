@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo Single point test: route marker 2
echo Required game process: Client-Win64-Shipping.exe
echo Limits: 8 steps, 25 seconds, F12 emergency stop.
choice /C YN /N /M "Start test? Press Y to continue, N to cancel: "
if errorlevel 2 exit /b 0
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" single-point --point 2 --execute --game-process Client-Win64-Shipping.exe --delay 15 %*
pause
endlocal
