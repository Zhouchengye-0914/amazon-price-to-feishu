@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_html_server.ps1"
exit /b %errorlevel%
