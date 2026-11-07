@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u retry_acoustic_nights.py 20261027 20261030 20261031 20261101 20261102 20261105
if errorlevel 1 goto done
start "" "..\Matched\Acoustic\index.html"
:done
pause
