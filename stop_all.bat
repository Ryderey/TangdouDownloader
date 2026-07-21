@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo   糖豆MP3提取器 - 停止所有服务
echo ========================================
echo.

:: 通过窗口标题关闭进程
taskkill /fi "WINDOWTITLE eq 糖豆MP3提取器 - Web服务*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq 糖豆MP3提取器 - Worker*" /t /f >nul 2>&1

:: 通过进程命令行关闭（备用方案）
wmic process where "commandline like '%%wsgi.py%%' and name='python.exe'" call terminate >nul 2>&1
wmic process where "commandline like '%%local_worker.py%%' and name='python.exe'" call terminate >nul 2>&1

echo [完成] 所有服务已停止
pause
