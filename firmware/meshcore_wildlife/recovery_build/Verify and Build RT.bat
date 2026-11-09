@echo off
setlocal
set "RT_PROJECT=%USERPROFILE%\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor"
py "%~dp0verify_and_build.py" "%RT_PROJECT%"
if errorlevel 1 echo Build or verification failed. See the message above. Nothing was flashed.
pause
