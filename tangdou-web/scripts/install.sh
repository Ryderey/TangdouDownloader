#!/bin/bash

# 糖豆MP3提取器 - Ubuntu 安装脚本
# 使用 uv 管理虚拟环境，非标准端口避免冲突

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 安装脚本"
echo "=========================================="
echo ""

# 检查是否为root用户
if [ "$EUID" -eq 0 ]; then 
   echo "❌ 请不要以root用户运行此脚本"
   exit 1
fi

# 获取脚本所在目录（即代码所在目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 代码目录是脚本的上级目录（scripts/install.sh 在代码目录下的 scripts/ 中）
CODE_DIR="$(dirname "$SCRIPT_DIR")"

echo "📁 检测到代码目录: $CODE_DIR"
echo ""

# 验证代码目录结构
if [ ! -f "$CODE_DIR/app.py" ] || [ ! -f "$CODE_DIR/wsgi.py" ]; then
    echo "❌ 错误：无法找到 app.py 或 wsgi.py"
    echo "   请确保从项目目录运行此脚本"
    echo "   正确示例：cd /path/to/tangdou-web && sudo bash scripts/install.sh"
    exit 1
fi

echo "✅ 代码目录验证通过"
echo ""

# 配置 - 使用非标准端口避免冲突
APP_NAME="tangdou-mp3"
APP_DIR="/opt/$APP_NAME"
USER=$(whoami)

# 端口配置（使用非标准高位端口）
HTTP_PORT=18080           # Nginx 对外端口（避免80）
INTERNAL_PORT=15000       # Gunicorn 内部端口（避免5000/8000/8080等常用端口）

echo "📌 配置信息："
echo "   应用目录: $APP_DIR"
echo "   外部端口: $HTTP_PORT"
echo "   内部端口: $INTERNAL_PORT"
echo ""

echo "[1/10] 更新系统软件包..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "[2/10] 安装系统依赖..."
sudo apt install -y \
    python3 \
    ffmpeg \
    git \
    nginx \
    curl \
    wget \
    rsync

# 检查FFmpeg版本
echo ""
echo "FFmpeg版本："
ffmpeg -version | head -1

echo ""
echo "[3/10] 安装 uv (Python包管理器)..."
if ! command -v uv &> /dev/null; then
    echo "   正在安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 添加 uv 到当前会话的 PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    echo "✅ uv 安装完成"
else
    echo "✅ uv 已安装"
fi

# 确保 uv 可用
if ! command -v uv &> /dev/null; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi
uv --version

echo ""
echo "[4/10] 安装Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "✅ Tailscale 安装完成"
else
    echo "✅ Tailscale 已安装"
fi

echo ""
echo "[5/10] 创建应用目录..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

echo ""
echo "[6/10] 复制代码文件到 $APP_DIR..."

# 使用 rsync 复制代码（排除不必要的文件）
rsync -av --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='static/downloads/*' \
    --exclude='.env' \
    "$CODE_DIR/" "$APP_DIR/"

# 确保 downloads 目录存在（但里面的文件不复制）
mkdir -p "$APP_DIR/static/downloads"
touch "$APP_DIR/static/downloads/.gitkeep"

# 设置权限
sudo chown -R $USER:$USER $APP_DIR

echo "✅ 代码复制完成"
echo ""

echo "[7/10] 使用 uv 创建 Python 虚拟环境..."
cd $APP_DIR

# 使用 uv 创建虚拟环境（默认目录名为 .venv）
uv venv

# 激活虚拟环境
source .venv/bin/activate

echo ""
echo "[8/10] 使用 uv 安装 Python 依赖..."
# 使用 uv pip 安装（比 pip 快 10-100 倍）
uv pip install flask gunicorn requests beautifulsoup4 lxml

echo ""
echo "[9/10] 创建启动脚本..."

# 创建 Gunicorn 启动配置
cat > $APP_DIR/gunicorn.conf.py << EOF
# Gunicorn 配置
bind = "127.0.0.1:$INTERNAL_PORT"
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 300
keepalive = 5
errorlog = "/var/log/tangdou/error.log"
accesslog = "/var/log/tangdou/access.log"
capture_output = True
enable_stdio_inheritance = True
EOF

# 创建 systemd 服务文件
sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null << EOF
[Unit]
Description=Tangdou MP3 Extractor Web
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin:$HOME/.cargo/bin"
Environment="PYTHONPATH=$APP_DIR"
Environment="FLASK_ENV=production"
ExecStart=$APP_DIR/.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "[10/10] 配置 Nginx（端口: $HTTP_PORT）..."

# 创建日志目录
sudo mkdir -p /var/log/tangdou
sudo chown $USER:$USER /var/log/tangdou

# 配置 Nginx - 使用非标准端口
sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null << EOF
server {
    listen $HTTP_PORT;
    server_name _;
    
    # 允许大文件下载
    client_max_body_size 100M;
    proxy_max_temp_file_size 100M;
    
    # 静态文件
    location /static/ {
        alias $APP_DIR/static/;
        expires 1h;
    }
    
    # 下载文件特殊处理
    location /api/download/ {
        alias $APP_DIR/static/downloads/;
        add_header Content-Disposition "attachment";
        add_header Cache-Control "no-cache";
    }
    
    # 反向代理到 Gunicorn
    location / {
        proxy_pass http://127.0.0.1:$INTERNAL_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket 支持（用于未来扩展）
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 长连接超时
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

# 启用站点
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
# 删除默认站点（可选，避免冲突）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试 Nginx 配置
sudo nginx -t

echo ""
echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""
echo "📋 下一步操作："
echo ""
echo "1️⃣  启动 Tailscale 内网穿透："
echo "    sudo tailscale up"
echo ""
echo "2️⃣  启动服务："
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable $APP_NAME"
echo "    sudo systemctl start $APP_NAME"
echo "    sudo systemctl restart nginx"
echo ""
echo "3️⃣  查看状态："
echo "    sudo systemctl status $APP_NAME"
echo "    sudo journalctl -u $APP_NAME -f"
echo ""
echo "4️⃣  手机/其他设备访问："
echo "    http://<Tailscale-IP>:$HTTP_PORT"
echo "    例如：http://100.x.x.x:$HTTP_PORT"
echo ""
echo "📁 应用目录: $APP_DIR"
echo "📜 日志文件: /var/log/tangdou/"
echo "🔌 外部端口: $HTTP_PORT (Nginx)"
echo "🔧 内部端口: $INTERNAL_PORT (Gunicorn)"
echo ""
echo "💡 如需修改端口，编辑："
echo "    $APP_DIR/gunicorn.conf.py (内部端口)"
echo "    /etc/nginx/sites-available/$APP_NAME (外部端口)"
echo ""
echo "📝 更新代码后重新部署："
echo "    sudo bash $CODE_DIR/scripts/install.sh"
echo ""
