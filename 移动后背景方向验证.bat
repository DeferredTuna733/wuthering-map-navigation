@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo One W step: 0.2 seconds. No mouse turn. F12 stops.
choice /C YN /N /M "Clear flat ground ahead? Press Y to start, N to cancel: "
if errorlevel 2 exit /b 0
"%~dp0venv\Scripts\python.exe" -u -B -m tools.background_step_probe --execute --delay 15
pause
