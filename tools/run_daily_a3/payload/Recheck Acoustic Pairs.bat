@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u acoustic_pairs.py %*
if errorlevel 1 echo Acoustic review needs attention; read the message above.
pause
