@echo off
cd /d "%~dp0"
py -3 install.py
if errorlevel 1 echo Installation failed. See the error above.
pause
