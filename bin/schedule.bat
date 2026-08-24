@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0.."
set "TASK_RUNNER=%PROJECT_ROOT%\bin\scheduled_run.bat"

if "%1"=="--install" (
    schtasks /Create /TN "AmazonDaily_0800" /TR ""%TASK_RUNNER%"" /SC DAILY /ST 08:00 /F
    schtasks /Create /TN "AmazonDaily_1600" /TR ""%TASK_RUNNER%"" /SC DAILY /ST 16:00 /F
    pause
    exit /b 0
)

if "%1"=="--remove" (
    schtasks /Delete /TN "AmazonDaily_0800" /F
    schtasks /Delete /TN "AmazonDaily_1600" /F
    pause
    exit /b 0
)

echo 参数错误。
exit /b 1
