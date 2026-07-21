@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo   Tangdou MP3 Extractor - Stop All
echo ========================================
echo.

:: Kill by window title
taskkill /fi "WINDOWTITLE eq Tangdou MP3 Extractor - Web*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Tangdou MP3 Extractor - Worker*" /t /f >nul 2>&1

:: Kill by command line (fallback)
wmic process where "commandline like '%%wsgi.py%%' and name='python.exe'" call terminate >nul 2>&1
wmic process where "commandline like '%%local_worker.py%%' and name='python.exe'" call terminate >nul 2>&1

echo [DONE] All services stopped
pause
