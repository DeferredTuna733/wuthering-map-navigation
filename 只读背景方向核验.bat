@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -u -B -m tools.check_background_heading --robust --alignment-limit 12 --capture --delay 15
pause
