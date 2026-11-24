@echo off
py -3 -u "%~dp0receiver.py" %*
if errorlevel 1 pause
