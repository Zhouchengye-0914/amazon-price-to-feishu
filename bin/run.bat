@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app\run.py %*
) else (
    echo [错误] 尚未部署，请先运行启动中心并选择首次部署。
    exit /b 1
)
exit /b %errorlevel%
