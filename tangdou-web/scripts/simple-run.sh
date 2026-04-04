#!/bin/bash

# 糖豆MP3提取器 - 简单运行脚本
# 不安装系统服务，直接在 /opt 或其他目录下运行

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 简单运行"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="$(dirname "$SCRIPT_DIR")"

# 检查 uv 是否安装
if ! command -v uv &> /dev/null; then
    echo "⚠️  未检测到 uv，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo "✅ uv 安装完成"
fi

# 确保 uv 可用
if ! command -v uv &> /dev/null; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "📁 代码目录: $CODE_DIR"
echo ""

# 检查代码完整性
if [ ! -f "$CODE_DIR/app.py" ]; then
    echo "❌ 错误：无法找到 app.py"
    echo "   请确保脚本在 tangdou-web/scripts/ 目录下"
    exit 1
fi

echo "[1/3] 检查依赖..."
cd $CODE_DIR

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "   创建虚拟环境..."
    uv venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 检查 Flask 是否安装
if ! python -c "import flask" 2>/dev/null; then
    echo "   安装依赖..."
    uv pip install flask gunicorn requests beautifulsoup4 lxml
fi

echo "✅ 依赖检查完成"
echo ""

# 创建下载目录
mkdir -p static/downloads

echo "[2/3] 选择运行方式："
echo ""
echo "  1) 开发模式 (flask run) - 适合调试，自动重载"
echo "  2) 生产模式 (gunicorn) - 适合长期使用"
echo ""
read -p "请选择 [1/2] (默认: 1): " choice
choice=${choice:-1}

echo ""
echo "[3/3] 启动服务..."
echo ""

if [ "$choice" = "2" ]; then
    # 生产模式
    PORT=${1:-18080}
    echo "🚀 生产模式启动 (端口: $PORT)"
    echo "   访问地址: http://<服务器IP>:$PORT"
    echo ""
    
    # 使用 gunicorn 启动
    .venv/bin/gunicorn \
        --bind "0.0.0.0:$PORT" \
        --workers 2 \
        --timeout 300 \
        --access-logfile - \
        --error-logfile - \
        wsgi:app
else
    # 开发模式
    echo "🚀 开发模式启动"
    echo "   访问地址: http://<服务器IP>:5000"
    echo ""
    
    export FLASK_APP=app.py
    export FLASK_ENV=development
    .venv/bin/flask run --host=0.0.0.0 --port=5000 --reload
fi
