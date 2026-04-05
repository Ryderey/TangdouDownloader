#!/bin/bash
# 启动 Tangdou MP3 服务

PROJECT_DIR="/home/ryl/script/tangdou-web"
cd "$PROJECT_DIR" || exit 1

# 确保日志目录存在
mkdir -p logs

echo "=========================================="
echo "启动 Tangdou MP3 服务"
echo "=========================================="
echo ""

# 停止现有进程
echo "[0/2] 停止现有进程..."
pkill -f "gunicorn" 2>/dev/null || true
pkill -f "rq_worker.py" 2>/dev/null || true
sleep 2

# 启动 Web 服务
echo ""
echo "[1/2] 启动 Web 服务..."
cd "$PROJECT_DIR"
.venv/bin/python -m gunicorn \
    --bind 0.0.0.0:18080 \
    --workers 2 \
    --timeout 300 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    wsgi:app &

WEB_PID=$!
sleep 2

if ps -p $WEB_PID > /dev/null; then
    echo "✓ Web 服务启动成功 (PID: $WEB_PID)"
else
    echo "✗ Web 服务启动失败"
    cat logs/error.log 2>/dev/null || echo "无错误日志"
    exit 1
fi

# 启动 Worker
echo ""
echo "[2/2] 启动 Worker..."
cd "$PROJECT_DIR"
.venv/bin/python scripts/rq_worker.py &

WORKER_PID=$!
sleep 3

if ps -p $WORKER_PID > /dev/null; then
    echo "✓ Worker 启动成功 (PID: $WORKER_PID)"
else
    echo "✗ Worker 启动失败"
    cat logs/worker.out 2>/dev/null || echo "无错误日志"
    exit 1
fi

echo ""
echo "=========================================="
echo "服务启动成功！"
echo "=========================================="
echo ""
echo "Web:    http://localhost:18080"
echo "查看日志:"
echo "  tail -f logs/access.log"
echo "  tail -f logs/worker.out"
echo ""
echo "停止服务:"
echo "  pkill -f gunicorn"
echo "  pkill -f rq_worker.py"
