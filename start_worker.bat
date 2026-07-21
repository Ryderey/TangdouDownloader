@echo off
chcp 65001 >nul 2>&1
title 糖豆MP3提取器 - Worker

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行 setup.bat
    pause
    exit /b 1
)

echo [启动] 糖豆MP3提取器 本地队列Worker
echo [提示] 按 Ctrl+C 停止Worker
echo.

.venv\Scripts\python.exe scripts\local_worker.py
