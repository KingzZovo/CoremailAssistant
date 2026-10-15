@echo off
chcp 65001 >nul
title Coremail 邮件自动处理工具 - 环境安装

echo =======================================================
echo    论客邮箱 (Coremail) 邮件自动处理工具 - 环境安装脚本
echo =======================================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并将其勾选加入系统 PATH 环境变量。
    echo 官方下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 检测到系统 Python 环境:
python --version

:: 切换到项目根目录
cd /d "%~dp0\.."

:: 创建虚拟环境
if not exist ".venv" (
    echo.
    echo [2/4] 正在创建虚拟环境 (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
) else (
    echo.
    echo [2/4] 虚拟环境 (.venv) 已存在，跳过创建。
)

:: 激活虚拟环境并安装依赖
echo.
echo [3/4] 正在安装与配置依赖项...
call .venv\Scripts\activate.bat

if exist "wheels" (
    echo [提示] 检测到本地 wheels 离线依赖目录，正在执行离线安装（纯内网免下载模式）...
    pip install --no-index --find-links=wheels -r requirements.txt
) else (
    echo [提示] 正在使用国内镜像加速下载依赖...
    python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn >nul 2>&1
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if %errorlevel% neq 0 (
        echo [提示] 尝试通过官方默认源重试安装...
        pip install -r requirements.txt
    )
)

:: 初始化配置文件
echo.
echo [4/4] 检查并初始化配置文件...
if not exist "config\config.yaml" (
    if exist "config\config.example.yaml" (
        copy "config\config.example.yaml" "config\config.yaml" >nul
        echo [提示] 已根据 config.example.yaml 创建 config\config.yaml
    )
)
if not exist "config\rules.yaml" (
    if exist "config\rules.example.yaml" (
        copy "config\rules.example.yaml" "config\rules.yaml" >nul
        echo [提示] 已根据 rules.example.yaml 创建 config\rules.yaml
    )
)
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [提示] 已根据 .env.example 创建 .env
    )
)

echo.
echo =======================================================
echo  安装完成！
echo  请在 config\config.yaml 或 .env 中填写您的论客邮箱账号和密码
echo  然后双击 scripts\run_windows.bat 启动程序。
echo =======================================================
pause
