#!/bin/bash

# 糖豆MP3提取器 - Ubuntu 安装脚本
# 功能：安装依赖、配置服务、设置Tailscale

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

# 配置
APP_NAME="tangdou-mp3"
APP_DIR="/opt/$APP_NAME"
USER=$(whoami)

echo "[1/8] 更新系统软件包..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "[2/8] 安装系统依赖..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    git \
    nginx \
    curl \
    wget

# 检查FFmpeg版本
echo ""
echo "FFmpeg版本："
ffmpeg -version | head -1

echo ""
echo "[3/8] 安装Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "✅ Tailscale安装完成"
else
    echo "✅ Tailscale已安装"
fi

echo ""
echo "[4/8] 创建应用目录..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# 创建下载目录
mkdir -p $APP_DIR/static/downloads

echo ""
echo "[5/8] 创建Python虚拟环境..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

echo ""
echo "[6/8] 安装Python依赖..."
pip install --upgrade pip
pip install flask gunicorn requests beautifulsoup4 lxml

echo ""
echo "[7/8] 创建启动脚本..."

# 创建Gunicorn启动配置
cat > $APP_DIR/gunicorn.conf.py << 'EOF'
# Gunicorn配置
bind = "127.0.0.1:5000"
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

# 创建systemd服务文件
sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null << EOF
[Unit]
Description=Tangdou MP3 Extractor Web
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="PYTHONPATH=$APP_DIR"
Environment="FLASK_ENV=production"
ExecStart=$APP_DIR/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "[8/8] 配置Nginx..."

# 创建日志目录
sudo mkdir -p /var/log/tangdou
sudo chown $USER:$USER /var/log/tangdou

# 配置Nginx
sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null << EOF
server {
    listen 80;
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
    
    # 反向代理到Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket支持（用于未来扩展）
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
sudo rm -f /etc/nginx/sites-enabled/default

# 测试Nginx配置
sudo nginx -t

echo ""
echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""
echo "📋 下一步操作："
echo ""
echo "1️⃣  启动Tailscale内网穿透："
echo "    sudo tailscale up"
echo ""
echo "2️⃣  将项目代码复制到 $APP_DIR"
echo "    例如：scp -r ./tangdou-web/* user@server:$APP_DIR/"
echo ""
echo "3️⃣  启动服务："
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable $APP_NAME"
echo "    sudo systemctl start $APP_NAME"
echo "    sudo systemctl restart nginx"
echo ""
echo "4️⃣  查看状态："
echo "    sudo systemctl status $APP_NAME"
echo "    sudo journalctl -u $APP_NAME -f"
echo ""
echo "5️⃣  手机访问Tailscale分配的IP即可使用"
echo ""
echo "📁 应用目录: $APP_DIR"
echo "📜 日志文件: /var/log/tangdou/"
echo ""
