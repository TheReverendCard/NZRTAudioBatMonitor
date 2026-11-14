@echo off
cd /d "%~dp0"
py -3 apply_serial_fix.py %*
pause
