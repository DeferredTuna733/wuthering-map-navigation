@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0venv\Scripts\pythonw.exe' -ArgumentList '-B','-m','app.navigation.ai_single_point','--from-point','2','--through-point','7' -WorkingDirectory '%~dp0' -WindowStyle Hidden -Verb RunAs"
endlocal
