@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0..\src;%PYTHONPATH%

title Coremail 邮件自动处理工具 - 试运行模式 (Dry-Run)

cd /d "%~dp0\.."

if not exist ".venv\Scripts\activate.bat" (
    echo [提示] 尚未初始化环境，正在自动执行安装脚本...
    call scripts\install_windows.bat
)

call .venv\Scripts\activate.bat

echo =======================================================
echo    试运行模式 (Dry-Run): 仅匹配规则，不修改已读状态与保存文件
echo =======================================================
echo.

python -m coremail_processor --dry-run --once

echo.
echo [完成] 试运行检查已结束。
pause
