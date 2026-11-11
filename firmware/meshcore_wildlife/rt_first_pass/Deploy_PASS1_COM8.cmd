@echo off
setlocal
cd /d "%~dp0"
set "project=%USERPROFILE%\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor"
if not "%~1"=="" set "project=%~1"
if not exist "changes.json" goto extract
py -3 install.py "%project%"
if errorlevel 1 goto fail
py -3 -m platformio run -d "%project%" -e NZRT_Xiao_S3_WIO_wildlife_repeater -t upload --upload-port COM8
if errorlevel 1 goto fail
py -3 field_check.py
if errorlevel 1 goto fail
pause
exit /b 0
:extract
echo Extract All files before running.
:fail
echo The firmware or field check was not verified. See the first error above.
pause
exit /b 1
