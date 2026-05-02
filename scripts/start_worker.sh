#!/bin/bash
# RQ Worker 启动脚本（支持uv和venv）

PROJECT_DIR="/home/ryl/script/tangdou-web"
cd "$PROJECT_DIR"

# 检测虚拟环境
if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [ -f "$PROJECT_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON="$PROJECT_DIR/.venv/Scripts/python.exe"
else
    PYTHON="python3"
fi

# 确保logs目录存在
mkdir -p "$PROJECT_DIR/logs"

# 启动RQ Worker
exec "$PYTHON" scripts/rq_worker.py
