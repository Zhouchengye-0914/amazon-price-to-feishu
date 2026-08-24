@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%PROJECT_ROOT%\app"

if not exist .venv\Scripts\python.exe (
    echo [错误] 尚未部署。
    pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'app');from config import load_config;load_config();from amazon.crawler import AmazonBrowser;from feishu import FeishuClient;print('配置和模块正常')"
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m unittest discover -s tests -q
if errorlevel 1 goto :failed

echo [成功] 设备验收通过。
pause
exit /b 0

:failed
echo [失败] 验收未通过。
pause
exit /b 1
