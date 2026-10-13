@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -u -B -m tools.monitor_navigation --capture --delay 15 --seconds 20
pause
