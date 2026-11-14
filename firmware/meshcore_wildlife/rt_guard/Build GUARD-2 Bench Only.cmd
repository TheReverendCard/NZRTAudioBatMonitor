@echo off
setlocal
cd /d "%~dp0"
py -3 prepare_build.py %*
set "rc=%ERRORLEVEL%"
if not "%rc%"=="0" echo Build not verified. See the first error and guard_build.log if present.
pause
exit /b %rc%
