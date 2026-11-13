@echo off
setlocal
py -3 "%~dp0install.py" %*
set "result=%errorlevel%"
pause
exit /b %result%
