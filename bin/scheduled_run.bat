@echo off
set "PROJECT_ROOT=%~dp0.."
powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\bin\scheduled_run.ps1"
exit /b %errorlevel%
