@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found, run setup.bat first
    pause
    exit /b 1
)

echo ========================================
echo   Tangdou MP3 Extractor - Start All
echo ========================================
echo.

:: Start Worker (new window)
echo [START] Worker...
start "Tangdou MP3 Extractor - Worker" cmd /c "cd /d "%~dp0" && .venv\Scripts\python.exe scripts\local_worker.py"

:: Wait 1s for Worker to start
timeout /t 1 /nobreak >nul

:: Start Web (new window)
echo [START] Web...
start "Tangdou MP3 Extractor - Web" cmd /c "cd /d "%~dp0" && .venv\Scripts\python.exe wsgi.py"

echo.
echo [DONE] All services started
echo [URL]  http://localhost:18080
echo.
echo Run stop_all.bat or close windows to stop
pause
