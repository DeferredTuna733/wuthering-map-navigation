@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -B -m tools.scan_labeler
pause
