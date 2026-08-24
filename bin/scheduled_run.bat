@echo off
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
.venv\Scripts\python.exe app\run.py
exit /b %errorlevel%
