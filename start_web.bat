@echo off
chcp 65001 >nul 2>&1
title 糖豆MP3提取器 - Web服务

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行 setup.bat
    pause
    exit /b 1
)

echo [启动] 糖豆MP3提取器 Web服务 (waitress)
echo [地址] http://localhost:18080
echo [提示] 按 Ctrl+C 停止服务
echo.

.venv\Scripts\python.exe wsgi.py
