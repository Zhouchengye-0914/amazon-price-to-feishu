@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python 3.10+，或未加入 PATH。
    pause
    exit /b 1
)

if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto :failed

.venv\Scripts\python.exe -m pip install -r config\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :failed

echo [成功] 部署完成。请配置 config\config.json 后运行验收。
pause
exit /b 0

:failed
echo [失败] 部署未完成，请检查上方错误。
pause
exit /b 1
