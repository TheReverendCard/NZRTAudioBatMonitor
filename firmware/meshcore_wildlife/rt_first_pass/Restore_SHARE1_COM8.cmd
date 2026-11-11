@echo off
setlocal
cd /d "%~dp0"
set "project=%USERPROFILE%\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor"
if not "%~1"=="" set "project=%~1"
py -3 install.py "%project%" --restore
if errorlevel 1 goto fail
py -3 -m platformio run -d "%project%" -e NZRT_Xiao_S3_WIO_wildlife_repeater -t upload --upload-port COM8
if errorlevel 1 goto fail
echo Restored SHARE-1 firmware. Check receiver and nzrt day after reboot.
pause
exit /b 0
:fail
echo Restore incomplete. Check the error above.
pause
exit /b 1
