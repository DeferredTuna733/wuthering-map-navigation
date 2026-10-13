@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -u -B -m tools.monitor_ai_heading --delay 15 --seconds 60 --coordinates
pause
