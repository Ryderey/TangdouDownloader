@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   Tangdou MP3 Extractor - Setup (Win10)
echo ========================================
echo.

cd /d "%~dp0"

:: Check uv
uv --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found. Install: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo         Or: pip install uv
    pause
    exit /b 1
)

echo [INFO] uv version:
uv --version
echo.

:: Create virtual environment
if exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment exists, skipping creation
) else (
    echo [SETUP] Creating virtual environment with uv...
    uv venv .venv --python 3.10
    if errorlevel 1 (
        echo [SETUP] Trying with default Python...
        uv venv .venv
        if errorlevel 1 (
            echo [ERROR] Failed to create virtual environment
            pause
            exit /b 1
        )
    )
    echo [DONE] Virtual environment created
)
echo.

:: Install dependencies
echo [SETUP] Installing dependencies...
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
if errorlevel 1 (
    echo [ERROR] Dependency installation failed
    pause
    exit /b 1
)
echo.

:: Check FFmpeg
if exist "bin\ffmpeg.exe" (
    echo [DONE] FFmpeg ready: bin\ffmpeg.exe
) else (
    echo [WARN] bin\ffmpeg.exe not found
    echo        Download FFmpeg and place ffmpeg.exe + ffprobe.exe in bin\
    echo        Or ensure FFmpeg is in system PATH
)
echo.

echo ========================================
echo   Setup complete!
echo   Start services: start_all.bat
echo ========================================
pause
