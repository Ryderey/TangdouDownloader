#!/bin/bash

# 糖豆MP3提取器 - 清理卸载脚本
# 用于完全删除服务和清理环境

set -e

echo "=========================================="
echo "  糖豆MP3提取器 - 清理卸载"
echo "=========================================="
echo ""

APP_NAME="tangdou-mp3"
APP_DIR_SYSTEM="/opt/$APP_NAME"
APP_DIR_USER="$HOME/$APP_NAME"

echo "⚠️  此操作将删除以下内容（如果存在）："
echo "   1. 系统级 systemd 服务: $APP_NAME"
echo "   2. 用户级 systemd 服务: $APP_NAME"
echo "   3. Nginx 配置: /etc/nginx/sites-available/$APP_NAME"
echo "   4. 系统应用目录: $APP_DIR_SYSTEM"
echo "   5. 用户应用目录: $APP_DIR_USER"
echo "   6. 日志文件: /var/log/tangdou/"
echo ""
read -p "确认删除? (输入 'yes' 继续): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ 已取消"
    exit 0
fi

echo ""
echo "[1/6] 停止并禁用系统级服务..."
sudo systemctl stop $APP_NAME 2>/dev/null || echo "   系统服务未运行"
sudo systemctl disable $APP_NAME 2>/dev/null || echo "   系统服务未启用"
sudo systemctl daemon-reload 2>/dev/null || true

echo ""
echo "[2/6] 停止并禁用用户级服务..."
systemctl --user stop $APP_NAME 2>/dev/null || echo "   用户服务未运行"
systemctl --user disable $APP_NAME 2>/dev/null || echo "   用户服务未启用"
systemctl --user daemon-reload 2>/dev/null || true

echo ""
echo "[3/6] 删除 systemd 服务文件..."
sudo rm -f /etc/systemd/system/$APP_NAME.service
rm -f "$HOME/.config/systemd/user/$APP_NAME.service"

echo ""
echo "[4/6] 删除 Nginx 配置..."
sudo rm -f /etc/nginx/sites-available/$APP_NAME
sudo rm -f /etc/nginx/sites-enabled/$APP_NAME

# 测试 nginx 配置
if sudo nginx -t 2>/dev/null; then
    echo "   重启 Nginx..."
    sudo systemctl restart nginx 2>/dev/null || true
else
    echo "   ⚠️  Nginx 配置测试失败，请手动检查"
fi

echo ""
echo "[5/6] 删除应用目录..."
if [ -d "$APP_DIR_SYSTEM" ]; then
    sudo rm -rf "$APP_DIR_SYSTEM"
    echo "   ✅ 已删除系统目录 $APP_DIR_SYSTEM"
else
    echo "   系统目录不存在，跳过"
fi

if [ -d "$APP_DIR_USER" ]; then
    rm -rf "$APP_DIR_USER"
    echo "   ✅ 已删除用户目录 $APP_DIR_USER"
else
    echo "   用户目录不存在，跳过"
fi

echo ""
echo "[6/6] 清理日志文件..."
read -p "   是否删除日志文件 /var/log/tangdou/? (y/n): " del_logs
if [ "$del_logs" = "y" ]; then
    sudo rm -rf /var/log/tangdou/
    echo "   ✅ 已删除系统日志"
else
    echo "   保留系统日志文件"
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
echo "  或使用: bash scripts/install-user-service.sh"
echo ""
