@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境不存在，请先运行 setup.bat
    pause
    exit /b 1
)

echo ========================================
echo   糖豆MP3提取器 - 启动所有服务
echo ========================================
echo.

:: 启动 Worker（新窗口）
echo [启动] Worker...
start "糖豆MP3提取器 - Worker" cmd /c "cd /d "%~dp0" && .venv\Scripts\python.exe scripts\local_worker.py"

:: 等待1秒让Worker先启动
timeout /t 1 /nobreak >nul

:: 启动 Web服务（新窗口）
echo [启动] Web服务...
start "糖豆MP3提取器 - Web服务" cmd /c "cd /d "%~dp0" && .venv\Scripts\python.exe wsgi.py"

echo.
echo [完成] 所有服务已启动
echo [地址] http://localhost:18080
echo.
echo 关闭服务请运行 stop_all.bat 或直接关闭对应窗口
pause
