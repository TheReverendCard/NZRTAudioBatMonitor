@echo off
setlocal
cd /d "%~dp0"
echo Close miniterm with Ctrl+] and leave the WiFi receiver running.
py -3 rt_compare.py %*
set "rc=%errorlevel%"
pause
exit /b %rc%
