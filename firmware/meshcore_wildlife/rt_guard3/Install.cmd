@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto done
.venv\Scripts\python.exe -m pip install platformio==6.1.18 pyserial==3.5 esptool==4.5.1 tzdata
:done
pause
