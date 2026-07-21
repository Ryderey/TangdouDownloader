@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   糖豆MP3提取器 - 环境安装 (Win7)
echo ========================================
echo.

cd /d "%~dp0"

:: 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8 并加入 PATH
    echo 下载地址: https://www.python.org/downloads/release/python-3810/
    pause
    exit /b 1
)

:: 显示 Python 版本
echo [信息] Python 版本:
python --version
echo.

:: 创建虚拟环境
if exist ".venv\Scripts\python.exe" (
    echo [信息] 虚拟环境已存在，跳过创建
) else (
    echo [安装] 正在创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [完成] 虚拟环境创建成功
)
echo.

:: 安装依赖
echo [安装] 正在安装依赖包...
.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo.

:: 检查 FFmpeg
if exist "bin\ffmpeg.exe" (
    echo [完成] FFmpeg 已就绪: bin\ffmpeg.exe
) else (
    echo [警告] 未找到 bin\ffmpeg.exe
    echo        请下载 FFmpeg Windows 版本并将 ffmpeg.exe、ffprobe.exe 放入 bin\ 目录
    echo        或确保 FFmpeg 已加入系统 PATH
)
echo.

echo ========================================
echo   安装完成！
echo   启动服务: start_all.bat
echo ========================================
pause
