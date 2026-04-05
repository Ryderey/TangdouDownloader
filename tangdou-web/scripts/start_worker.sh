#!/bin/bash
# RQ Worker 启动脚本（支持uv和venv）

PROJECT_DIR="/home/ryl/script/tangdou-web"
cd "$PROJECT_DIR"

# 检测虚拟环境
if [ -f "$PROJECT_DIR/.venv/bin/rq" ]; then
    RQ="$PROJECT_DIR/.venv/bin/rq"
elif [ -f "$PROJECT_DIR/.venv/Scripts/rq.exe" ]; then
    RQ="$PROJECT_DIR/.venv/Scripts/rq.exe"
else
    RQ="rq"
fi

# 确保logs目录存在
mkdir -p "$PROJECT_DIR/logs"

# 启动RQ Worker
# 注意：队列名 tangdou 是位置参数，不是 --queues 选项
exec "$RQ" worker \
    --name "tangdou-worker-$(hostname)" \
    --url "redis://localhost:6379/0" \
    --with-scheduler \
    --results-ttl 604800 \
    --job-ttl 3600 \
    --logging-level INFO \
    tangdou
