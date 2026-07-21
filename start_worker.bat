@echo off
chcp 65001 >nul 2>&1
title Tangdou MP3 Extractor - Worker

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found, run setup.bat first
    pause
    exit /b 1
)

echo [START] Tangdou MP3 Extractor Local Queue Worker
echo [STOP]  Press Ctrl+C to stop
echo.

.venv\Scripts\python.exe scripts\local_worker.py
