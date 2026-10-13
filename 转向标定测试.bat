@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator permission...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
echo.
echo Mouse-only turning probe. NO W key or walking.
echo Right 120 relative units, pause, left 120 relative units.
echo F12 stops immediately.
echo.
choice /C YN /N /M "Start mouse-only test? Press Y to start, N to cancel: "
if errorlevel 2 (
    echo Cancelled.
    pause
    exit /b 0
)
"%~dp0venv\Scripts\python.exe" -B "%~dp0run.py" turning-probe --execute --game-process Client-Win64-Shipping.exe --delay 15
set RESULT=%errorlevel%
echo.
echo Test process exited with code %RESULT%.
pause
endlocal
exit /b %RESULT%
