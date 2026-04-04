#!/bin/bash

# 快速部署脚本 - 假设代码已在 /opt/tangdou-mp3

APP_NAME="tangdou-mp3"

echo "🚀 部署糖豆MP3提取器..."

# 重新加载systemd
sudo systemctl daemon-reload

# 启动/重启服务
sudo systemctl restart $APP_NAME
sudo systemctl restart nginx

# 检查状态
echo ""
echo "📊 服务状态："
sudo systemctl status $APP_NAME --no-pager

echo ""
echo "✅ 部署完成！"
echo "🌐 访问地址: http://$(hostname -I | awk '{print $1}')"
