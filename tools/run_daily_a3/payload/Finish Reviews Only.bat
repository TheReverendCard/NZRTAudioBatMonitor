@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u finish_daily_reviews.py
if errorlevel 1 echo Final review needs attention. Read the output above.
pause
