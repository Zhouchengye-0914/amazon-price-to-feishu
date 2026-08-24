@echo off
chcp 65001 >nul
cd /d "%~dp0"

:menu
cls
echo ================================================
echo       Amazon Daily 启动中心
echo ================================================
echo   1. 首次部署 / 更新依赖
echo   2. 部署验收
echo   3. PD03 实时验证
echo   4. 全量实时运行
echo   5. 注册每日 08:00 / 16:00 计划任务
echo   6. 删除计划任务
echo   7. 打开操作手册
echo   0. 退出
echo ================================================
set /p choice=请选择: 

if "%choice%"=="1" call bin\setup.bat
if "%choice%"=="2" call bin\verify.bat
if "%choice%"=="3" call bin\run.bat --sheets PD03 --force-fetch
if "%choice%"=="4" call bin\run.bat --force-fetch
if "%choice%"=="5" call bin\schedule.bat --install
if "%choice%"=="6" call bin\schedule.bat --remove
if "%choice%"=="7" start "" docs\操作手册.md
if "%choice%"=="0" exit /b 0
goto menu
