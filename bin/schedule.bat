@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0schedule.ps1" -Action "%1"
exit /b %errorlevel%
