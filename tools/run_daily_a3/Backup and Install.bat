@echo off
cd /d "%~dp0"
py -3 install.py --apply %*
if errorlevel 1 echo Update needs attention. Read the message above.
pause
