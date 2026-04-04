#!/bin/bash

# 糖豆MP3提取器 - Ubuntu 系统服务安装脚本
# 可选：安装到系统目录（需要root）或用户目录（无需root）

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 系统服务安装"
echo "=========================================="
echo ""

# 检查是否为root用户
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  警告：当前以 root 用户运行"
   echo "   建议用普通用户运行，脚本会自动使用 sudo"
   echo ""
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# 选择安装方式
echo "请选择安装方式："
echo ""
echo "  1) 系统目录安装 (/opt/$APP_NAME) - 需要 sudo，适合服务器"
echo "  2) 用户目录安装 ($HOME/$APP_NAME) - 无需 sudo，适合个人使用"
echo ""
read -p "请选择 [1/2] (默认: 2): " install_choice
install_choice=${install_choice:-2}

if [ "$install_choice" = "1" ]; then
    # 系统目录安装
    APP_NAME="tangdou-mp3"
    APP_DIR="/opt/$APP_NAME"
    USE_SUDO="sudo"
    echo ""
    echo "📌 系统目录安装模式: $APP_DIR"
else
    # 用户目录安装
    APP_NAME="tangdou-mp3"
    APP_DIR="$HOME/$APP_NAME"
    USE_SUDO=""
    echo ""
    echo "📌 用户目录安装模式: $APP_DIR"
fi

# 端口配置（使用非标准高位端口）
HTTP_PORT=18080           # Nginx 对外端口（避免80）
INTERNAL_PORT=15000       # Gunicorn 内部端口（避免常用端口）

echo "   外部端口: $HTTP_PORT"
echo "   内部端口: $INTERNAL_PORT"
echo ""

# 如果是系统安装，检查 sudo 权限
if [ "$install_choice" = "1" ] && [ "$EUID" -ne 0 ]; then
    echo "🔐 需要 sudo 权限进行系统安装..."
    sudo -v || { echo "❌ 无法获取 sudo 权限"; exit 1; }
fi

echo "[1/10] 更新系统软件包..."
$USE_SUDO apt update
$USE_SUDO apt upgrade -y

echo ""
echo "[2/10] 安装系统依赖..."
$USE_SUDO apt install -y \
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
$USE_SUDO mkdir -p "$APP_DIR"
$USE_SUDO chown $(whoami):$(whoami) "$APP_DIR" 2>/dev/null || true

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

echo "✅ 代码复制完成"
echo ""

echo "[7/10] 使用 uv 创建 Python 虚拟环境..."
cd "$APP_DIR"

# 使用 uv 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

echo ""
echo "[8/10] 使用 uv 安装 Python 依赖..."
uv pip install flask gunicorn requests beautifulsoup4 lxml

echo ""
echo "[9/10] 创建启动配置..."

# 创建 Gunicorn 启动配置
cat > "$APP_DIR/gunicorn.conf.py" << EOF
# Gunicorn 配置
bind = "127.0.0.1:$INTERNAL_PORT"
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 300
keepalive = 5
errorlog = "$APP_DIR/logs/error.log"
accesslog = "$APP_DIR/logs/access.log"
capture_output = True
enable_stdio_inheritance = True
EOF

# 创建日志目录
mkdir -p "$APP_DIR/logs"

# 如果是系统安装，创建 systemd 服务
if [ "$install_choice" = "1" ]; then
    echo "   创建 systemd 服务..."
    
    $USE_SUDO tee /etc/systemd/system/$APP_NAME.service > /dev/null << EOF
[Unit]
Description=Tangdou MP3 Extractor Web
After=network.target

[Service]
Type=simple
User=$(whoami)
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
    
    # 创建日志目录（系统目录）
    $USE_SUDO mkdir -p /var/log/tangdou
    $USE_SUDO chown $(whoami):$(whoami) /var/log/tangdou 2>/dev/null || true
    
    # 更新 gunicorn 配置使用系统日志目录
    cat > "$APP_DIR/gunicorn.conf.py" << EOF
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

    # 配置 Nginx
    $USE_SUDO tee /etc/nginx/sites-available/$APP_NAME > /dev/null << EOF
server {
    listen $HTTP_PORT;
    server_name _;
    
    client_max_body_size 100M;
    proxy_max_temp_file_size 100M;
    
    location /static/ {
        alias $APP_DIR/static/;
        expires 1h;
    }
    
    location /api/download/ {
        alias $APP_DIR/static/downloads/;
        add_header Content-Disposition "attachment";
        add_header Cache-Control "no-cache";
    }
    
    location / {
        proxy_pass http://127.0.0.1:$INTERNAL_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

    # 启用站点
    $USE_SUDO ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
    $USE_SUDO rm -f /etc/nginx/sites-enabled/default
    
    # 测试 Nginx 配置
    $USE_SUDO nginx -t
    
    INSTALL_COMPLETE=true
else
    echo "[10/10] 用户目录安装，跳过 Nginx 配置..."
    echo "   使用 simple-run.sh 启动即可"
    INSTALL_COMPLETE=false
fi

echo ""
echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""

if [ "$install_choice" = "1" ]; then
    # 系统安装完成提示
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
    echo "4️⃣  访问地址："
    echo "    http://<服务器IP>:$HTTP_PORT"
    echo "    http://<Tailscale-IP>:$HTTP_PORT"
else
    # 用户安装完成提示
    echo "📋 启动方法："
    echo ""
    echo "1️⃣  使用 simple-run.sh 启动："
    echo "    cd $APP_DIR"
    echo "    sudo bash scripts/simple-run.sh"
    echo ""
    echo "2️⃣  或手动启动："
    echo "    cd $APP_DIR"
    echo "    source .venv/bin/activate"
    echo "    python app.py"
    echo ""
    echo "3️⃣  访问地址："
    echo "    http://<服务器IP>:5000"
fi

echo ""
echo "📁 应用目录: $APP_DIR"
echo "🔌 外部端口: $HTTP_PORT"
echo "🔧 内部端口: $INTERNAL_PORT"
echo ""
