@echo off
setlocal
cd /d "%~dp0"
if not exist "Run Daily Scan.bat" exit /b 1
cmd /d /c call "Run Daily Scan.bat" %*
set "daily_rc=%errorlevel%"
echo Save and close all Fast AviaNZ windows, then press a key to reconcile the reviews.
pause
".venv\Scripts\python.exe" -u finish_daily_reviews.py
set "final_rc=%errorlevel%"
echo Daily exit: %daily_rc%. Final review exit: %final_rc%.
pause
if not "%daily_rc%"=="0" exit /b %daily_rc%
exit /b %final_rc%
