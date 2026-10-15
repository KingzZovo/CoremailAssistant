@echo off
chcp 65001 >nul
title CoremailAssistant - 首次安装与启动向导

echo ========================================================
echo   CoremailAssistant 论客邮箱智能助手 - Windows 运行向导
echo ========================================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [1/2] 正在初始化 Python 独立虚拟环境并安装依赖...
    call scripts\install_windows.bat
)

echo.
echo [2/2] 正在启动 CoremailAssistant 桌面主程序...
call scripts\run_windows.bat
