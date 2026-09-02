@echo off
wscript.exe //B //NoLogo "%~dp0hidden_ps1.vbs" "%~dp0start_html_server.ps1"
exit /b %errorlevel%
