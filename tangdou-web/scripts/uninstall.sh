#!/bin/bash

# 糖豆MP3提取器 - 清理卸载脚本
# 用于完全删除服务和清理环境

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 清理卸载"
echo "=========================================="
echo ""

APP_NAME="tangdou-mp3"
APP_DIR="/opt/$APP_NAME"

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then 
   echo "⚠️  建议使用 sudo 运行此脚本以获得完全清理权限"
   echo ""
fi

echo "⚠️  此操作将删除以下内容："
echo "   1. systemd 服务: $APP_NAME"
echo "   2. Nginx 配置: /etc/nginx/sites-available/$APP_NAME"
echo "   3. 应用目录: $APP_DIR"
echo "   4. 日志文件: /var/log/tangdou/"
echo ""
read -p "确认删除? (输入 'yes' 继续): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ 已取消"
    exit 0
fi

echo ""
echo "[1/5] 停止并禁用服务..."
sudo systemctl stop $APP_NAME 2>/dev/null || echo "   服务未运行"
sudo systemctl disable $APP_NAME 2>/dev/null || echo "   服务未启用"
sudo systemctl daemon-reload

echo ""
echo "[2/5] 删除 systemd 服务文件..."
sudo rm -f /etc/systemd/system/$APP_NAME.service

echo ""
echo "[3/5] 删除 Nginx 配置..."
sudo rm -f /etc/nginx/sites-available/$APP_NAME
sudo rm -f /etc/nginx/sites-enabled/$APP_NAME

# 测试 nginx 配置
if sudo nginx -t 2>/dev/null; then
    echo "   重启 Nginx..."
    sudo systemctl restart nginx
else
    echo "   ⚠️  Nginx 配置测试失败，请手动检查"
fi

echo ""
echo "[4/5] 删除应用目录..."
if [ -d "$APP_DIR" ]; then
    sudo rm -rf $APP_DIR
    echo "   ✅ 已删除 $APP_DIR"
else
    echo "   目录不存在，跳过"
fi

echo ""
echo "[5/5] 清理日志文件..."
read -p "   是否删除日志文件 /var/log/tangdou/? (y/n): " del_logs
if [ "$del_logs" = "y" ]; then
    sudo rm -rf /var/log/tangdou/
    echo "   ✅ 已删除日志"
else
    echo "   保留日志文件"
fi

echo ""
echo "=========================================="
echo "  ✅ 清理完成！"
echo "=========================================="
echo ""
echo "系统已恢复干净状态。"
echo ""
echo "如需重新部署，只需将代码复制到任意目录，然后："
echo "  cd /path/to/tangdou-web && python app.py"
echo ""
