@echo off
py -3 "%~dp0export_and_queue.py" --root "%~dp0..\.." --mode run
set "rc=%errorlevel%"
pause
exit /b %rc%
