@echo off
setlocal
"%USERPROFILE%\Documents\Bat\BatDailyTool\.venv\Scripts\python.exe" -u "%USERPROFILE%\Documents\Bat\BatDailyTool\review_first_daily.py" --status
set "rc=%errorlevel%"
pause
exit /b %rc%
