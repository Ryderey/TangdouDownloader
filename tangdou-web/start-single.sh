#!/bin/bash
# 单 worker 模式启动脚本 - 避免多进程问题

cd /home/ryl/tangdou-mp3
source .venv/bin/activate

# 清除缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# 创建任务存储目录
mkdir -p static/downloads/.tasks

echo "🚀 启动服务（单 worker 模式）..."
echo "   访问地址: http://$(hostname -I | awk '{print $1}'):18080"
echo ""

# 使用单 worker，避免多进程内存不共享问题
exec .venv/bin/gunicorn \
    --bind 0.0.0.0:18080 \
    --workers 1 \
    --timeout 300 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    wsgi:app
