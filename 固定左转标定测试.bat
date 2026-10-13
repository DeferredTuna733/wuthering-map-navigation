@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo Fixed left turn: 240 relative units. NO W key or walking.
echo Do not move the mouse or press movement keys. F12 stops the test.
choice /C YN /N /M "Start? Press Y to continue, N to cancel: "
if errorlevel 2 exit /b 0
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" scan-sequence --execute --direction left --delay 15 --seconds 10 --pixels 240
pause
endlocal
