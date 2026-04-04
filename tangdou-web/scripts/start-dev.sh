#!/bin/bash

# 开发环境启动脚本

echo "🚀 启动糖豆MP3提取器（开发模式）"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖
pip install -q flask requests beautifulsoup4 lxml

# 检查FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ 警告：未检测到FFmpeg，请先安装"
    echo "   Ubuntu/Debian: sudo apt install ffmpeg"
    echo "   macOS: brew install ffmpeg"
    exit 1
fi

echo "✅ FFmpeg已安装"
echo "🌐 访问地址: http://localhost:5000"
echo ""

# 启动Flask
export FLASK_APP=app.py
export FLASK_ENV=development
export PYTHONPATH=$(pwd)

python -m flask run --host=0.0.0.0 --port=5000 --reload
