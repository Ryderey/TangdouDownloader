#!/bin/bash
# 停止所有服务

echo "停止 Tangdou MP3 服务..."

# 停止 Web 服务
pkill -f "gunicorn.*wsgi:app" 2>/dev/null && echo "✓ Web 服务已停止" || echo "! Web 服务未运行"

# 停止 Worker (Python 脚本方式)
pkill -f "rq_worker.py" 2>/dev/null && echo "✓ Worker 已停止" || echo "! Worker 未运行"

# 停止可能残留的 rq worker 进程
pkill -f "rq worker.*tangdou" 2>/dev/null || true

echo ""
echo "完成"
