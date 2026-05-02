#!/bin/bash

# 糖豆MP3提取器 - 排查调试脚本
# 用于查看各种日志和状态

echo "=========================================="
echo "  糖豆MP3提取器 - 排查工具"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="$(dirname "$SCRIPT_DIR")"

echo "📁 代码目录: $CODE_DIR"
echo ""

# 检查运行方式
if systemctl --user is-active tangdou-mp3 &>/dev/null; then
    SERVICE_TYPE="user"
    echo "✅ 检测到用户级服务正在运行"
elif systemctl is-active tangdou-mp3 &>/dev/null; then
    SERVICE_TYPE="system"
    echo "✅ 检测到系统级服务正在运行"
elif pgrep -f "python.*app.py" > /dev/null; then
    SERVICE_TYPE="manual"
    echo "✅ 检测到手动运行（python app.py）"
elif pgrep -f "gunicorn.*wsgi:app" > /dev/null; then
    SERVICE_TYPE="simple-run"
    echo "✅ 检测到 simple-run.sh 运行"
else
    SERVICE_TYPE="none"
    echo "⚠️  未检测到运行中的服务"
fi

echo ""
echo "=========================================="
echo "  选择要查看的日志："
echo "=========================================="
echo ""
echo "  1) Flask 应用日志（最近50行）"
echo "  2) systemd 服务日志"
echo "  3) 下载目录文件列表"
echo "  4) 检查端口占用"
echo "  5) 测试 API 接口"
echo "  6) 查看所有日志（完整）"
echo "  7) 启用 Flask 调试模式运行"
echo ""
read -p "请选择 [1-7]: " choice

case $choice in
    1)
        echo ""
        echo "📋 Flask 应用日志："
        echo "-------------------"
        if [ "$SERVICE_TYPE" = "user" ]; then
            journalctl --user -u tangdou-mp3 -n 50 --no-pager
        elif [ "$SERVICE_TYPE" = "system" ]; then
            sudo journalctl -u tangdou-mp3 -n 50 --no-pager
        elif [ "$SERVICE_TYPE" = "simple-run" ]; then
            echo "simple-run 模式日志在终端输出，请查看原终端"
        else
            echo "未检测到服务日志，尝试查看日志文件..."
            if [ -f "$CODE_DIR/logs/error.log" ]; then
                tail -n 50 "$CODE_DIR/logs/error.log"
            else
                echo "未找到日志文件"
            fi
        fi
        ;;
    
    2)
        echo ""
        echo "📋 systemd 服务状态："
        echo "---------------------"
        if [ "$SERVICE_TYPE" = "user" ]; then
            systemctl --user status tangdou-mp3 --no-pager
        elif [ "$SERVICE_TYPE" = "system" ]; then
            sudo systemctl status tangdou-mp3 --no-pager
        else
            echo "未使用 systemd 服务"
        fi
        ;;
    
    3)
        echo ""
        echo "📁 下载目录文件："
        echo "-----------------"
        ls -la "$CODE_DIR/static/downloads/" 2>/dev/null || echo "目录为空或不存在"
        ;;
    
    4)
        echo ""
        echo "🔌 端口占用情况："
        echo "-----------------"
        echo "端口 5000:"
        lsof -i :5000 2>/dev/null || echo "  未占用"
        echo "端口 18080:"
        lsof -i :18080 2>/dev/null || echo "  未占用"
        echo "端口 15000:"
        lsof -i :15000 2>/dev/null || echo "  未占用"
        ;;
    
    5)
        echo ""
        echo "🧪 测试 API 接口："
        echo "------------------"
        
        # 检测端口
        PORT=5000
        if lsof -i :18080 > /dev/null 2>&1; then
            PORT=18080
        fi
        
        echo "测试 http://localhost:$PORT/"
        curl -s -o /dev/null -w "首页状态: %{http_code}\n" http://localhost:$PORT/
        
        echo ""
        echo "提交测试任务..."
        TEST_RESULT=$(curl -s -X POST http://localhost:$PORT/api/submit \
            -H "Content-Type: application/json" \
            -d '{"url":"test123"}' 2>/dev/null)
        echo "响应: $TEST_RESULT"
        ;;
    
    6)
        echo ""
        echo "📜 完整日志（按 Ctrl+C 退出）："
        echo "-------------------------------"
        if [ "$SERVICE_TYPE" = "user" ]; then
            journalctl --user -u tangdou-mp3 -f
        elif [ "$SERVICE_TYPE" = "system" ]; then
            sudo journalctl -u tangdou-mp3 -f
        elif [ -f "$CODE_DIR/logs/error.log" ]; then
            tail -f "$CODE_DIR/logs/error.log"
        else
            echo "未找到日志文件"
        fi
        ;;
    
    7)
        echo ""
        echo "🐛 启动 Flask 调试模式..."
        echo "--------------------------"
        cd "$CODE_DIR"
        source .venv/bin/activate
        export FLASK_ENV=development
        export FLASK_DEBUG=1
        python app.py
        ;;
    
    *)
        echo "无效选择"
        ;;
esac
