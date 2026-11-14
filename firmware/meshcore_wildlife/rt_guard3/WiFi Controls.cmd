@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Install.cmd first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe optional_receiver\wifi_controls.py %*
pause
