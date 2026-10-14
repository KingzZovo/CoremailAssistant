@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

title CoremailAssistant 论客邮箱智能助手 - 运行中

cd /d "%~dp0\.."

if not exist ".venv\Scripts\activate.bat" (
    echo [提示] 尚未初始化环境，正在自动执行安装脚本...
    call scripts\install_windows.bat
)

call .venv\Scripts\activate.bat

echo =======================================================
echo    CoremailAssistant 论客邮箱智能协同与自动处理助手
echo =======================================================
echo.

if exist "main.py" (
    python main.py
) else (
    set PYTHONPATH=%~dp0..\src;%PYTHONPATH%
    python -m coremail_processor
)

if %errorlevel% neq 0 (
    echo.
    echo [提示] 程序退出，退出码: %errorlevel%
    pause
)
