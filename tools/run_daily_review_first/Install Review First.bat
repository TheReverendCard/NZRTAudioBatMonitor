@echo off
setlocal
"%USERPROFILE%\Documents\Bat\BatDailyTool\.venv\Scripts\python.exe" -u "%~dp0install_review_first.py" --tool "%USERPROFILE%\Documents\Bat\BatDailyTool"
set "rc=%errorlevel%"
pause
exit /b %rc%
