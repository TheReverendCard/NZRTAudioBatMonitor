@echo off
setlocal
cd /d "%~dp0"
set "project=%USERPROFILE%\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor"
set "rtport=COM8"
if not "%~1"=="" set "rtport=%~1"
if not "%~2"=="" set "project=%~2"
echo Applying LIVE-1 and uploading RT firmware on %rtport%.
py -3 install.py --project "%project%"
if errorlevel 1 goto failed
py -3 -m platformio run -d "%project%" -e NZRT_Xiao_S3_WIO_wildlife_repeater -t upload --upload-port %rtport%
if errorlevel 1 goto failed
py -3 field_check.py --port %rtport%
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo See the first error or unverified field result above.
pause
exit /b 1
