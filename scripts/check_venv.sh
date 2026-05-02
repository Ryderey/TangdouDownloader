#!/bin/bash
# 虚拟环境诊断脚本

echo "=========================================="
echo "  虚拟环境诊断"
echo "=========================================="
echo ""

PROJECT_DIR="/home/ryl/script/tangdou-web"
cd "$PROJECT_DIR" || exit 1

echo "[1] 项目目录: $PROJECT_DIR"
echo ""

# 检查 uv
echo "[2] uv 工具检查..."
if command -v uv &> /dev/null; then
    echo "  uv 路径: $(which uv)"
    echo "  uv 版本: $(uv --version)"
else
    echo "  ! uv 未安装"
fi
echo ""

# 检查虚拟环境
echo "[3] 虚拟环境检查..."
if [ -d ".venv" ]; then
    echo "  .venv 目录存在"
    
    # Python 解释器
    if [ -f ".venv/bin/python" ]; then
        echo "  Python: .venv/bin/python"
        echo "  Python 版本: $(.venv/bin/python --version 2>&1)"
    else
        echo "  ✗ Python 解释器不存在"
    fi
    
    # pip
    if [ -f ".venv/bin/pip" ]; then
        echo "  pip: .venv/bin/pip"
    else
        echo "  ! pip 不存在（uv环境通常没有pip）"
    fi
    
    # 已安装的包
    echo ""
    echo "[4] 已安装的包:"
    if command -v uv &> /dev/null; then
        uv pip list | grep -E "(redis|rq|gunicorn|flask)" || echo "  未找到相关包"
    elif [ -f ".venv/bin/pip" ]; then
        .venv/bin/pip list | grep -E "(redis|rq|gunicorn|flask)" || echo "  未找到相关包"
    fi
else
    echo "  ✗ .venv 目录不存在"
fi

echo ""
echo "[5] 系统 Python:"
echo "  路径: $(which python3)"
echo "  版本: $(python3 --version 2>&1)"

echo ""
echo "=========================================="
echo "常用命令:"
echo "=========================================="
echo ""
echo "使用 uv 安装依赖:"
echo "  uv pip install redis rq"
echo ""
echo "查看虚拟环境包列表:"
echo "  uv pip list"
echo ""
echo "验证导入:"
echo "  .venv/bin/python -c \"import redis, rq; print('OK')\""
echo ""
