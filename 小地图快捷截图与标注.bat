@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -u -B -m tools.scan_capture_station
pause
