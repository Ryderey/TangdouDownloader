#!/bin/bash

# 糖豆MP3提取器 - 用户级系统服务安装脚本
# 无需 sudo，支持后台常驻和开机自启

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 用户服务安装"
echo "=========================================="
echo ""

# 配置
APP_NAME="tangdou-mp3"
# 直接使用代码所在目录，不复制到固定位置
CODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="$CODE_DIR"

echo "📁 代码目录: $CODE_DIR"
echo ""

# 验证代码目录
if [ ! -f "$CODE_DIR/app.py" ]; then
    echo "❌ 错误：无法找到 app.py"
    exit 1
fi
PORT=${1:-18080}  # 默认端口 18080

echo "📌 安装信息："
echo "   运行目录: $INSTALL_DIR"
echo "   服务名称: $APP_NAME"
echo "   运行端口: $PORT"
echo ""

# 检查 systemd 是否支持用户服务
if [ -z "$XDG_RUNTIME_DIR" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id - u)"
fi

# 创建 systemd 用户目录
mkdir -p "$HOME/.config/systemd/user"

echo "[1/6] 检查依赖..."

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "   安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
export PATH="$HOME/.cargo/bin:$PATH"

# 检查 ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  警告：未检测到 FFmpeg，请先安装："
    echo "   sudo apt install ffmpeg"
    exit 1
fi

echo "✅ 依赖检查完成"
echo ""

echo "[2/6] 检查目录结构..."

# 确保 downloads 目录存在
mkdir -p "$INSTALL_DIR/static/downloads"
touch "$INSTALL_DIR/static/downloads/.gitkeep"

echo "✅ 目录检查完成"
echo ""

echo "[3/6] 创建 Python 虚拟环境..."
cd "$INSTALL_DIR"

uv venv
source .venv/bin/activate

echo ""
echo "[4/6] 安装依赖..."
uv pip install flask gunicorn requests beautifulsoup4 lxml

echo ""
echo "[5/6] 创建用户 systemd 服务..."

# 创建日志目录
mkdir -p "$INSTALL_DIR/logs"

# 创建启动脚本
cat > "$INSTALL_DIR/start.sh" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source .venv/bin/activate
exec .venv/bin/gunicorn \
    --bind "0.0.0.0:$PORT" \
    --workers 2 \
    --timeout 300 \
    --access-logfile "$INSTALL_DIR/logs/access.log" \
    --error-logfile "$INSTALL_DIR/logs/error.log" \
    wsgi:app
EOF
chmod +x "$INSTALL_DIR/start.sh"

# 创建 systemd 用户服务文件
mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/$APP_NAME.service" << EOF
[Unit]
Description=Tangdou MP3 Extractor Web (User Service)
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/.venv/bin:$HOME/.cargo/bin:$PATH"
Environment="PYTHONPATH=$INSTALL_DIR"
Environment="FLASK_ENV=production"
ExecStart=$INSTALL_DIR/start.sh
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

echo "✅ 服务文件创建完成"
echo ""

echo "[6/6] 启用开机自启..."

# 重新加载用户 systemd 配置
systemctl --user daemon-reload

# 启用服务（开机自启）
systemctl --user enable $APP_NAME

echo "✅ 开机自启已启用"
echo ""

echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""
echo "📋 服务管理命令（无需 sudo）："
echo ""
echo "  启动服务:  systemctl --user start $APP_NAME"
echo "  停止服务:  systemctl --user stop $APP_NAME"
echo "  重启服务:  systemctl --user restart $APP_NAME"
echo "  查看状态:  systemctl --user status $APP_NAME"
echo "  查看日志:  journalctl --user -u $APP_NAME -f"
echo ""
echo "🌐 访问地址:"
echo "  http://$(hostname -I | awk '{print $1}'):$PORT"
echo "  http://127.0.0.1:$PORT"
echo ""
echo "📁 运行目录: $INSTALL_DIR"
echo "📜 日志文件: $INSTALL_DIR/logs/"
echo ""
echo "⚠️  注意：用户服务默认在登出后停止"
echo "   如需登出后继续运行，执行："
echo "   sudo loginctl enable-linger $USER"
echo ""

# 询问是否立即启动
read -p "🚀 是否立即启动服务? [Y/n]: " start_now
start_now=${start_now:-Y}

if [ "$start_now" = "Y" ] || [ "$start_now" = "y" ]; then
    systemctl --user start $APP_NAME
    sleep 2
    echo ""
    echo "✅ 服务已启动"
    systemctl --user status $APP_NAME --no-pager
fi
