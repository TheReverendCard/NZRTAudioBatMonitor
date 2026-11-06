@echo off
cd /d "%~dp0"
py -m pip install platformio==6.1.18 pyserial tzdata
if errorlevel 1 goto done
py unpack_model.py
:done
pause
