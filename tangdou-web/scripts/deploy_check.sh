#!/bin/bash
# 部署前检查脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/home/ryl/script/tangdou-web"
ERRORS=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  部署前检查${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 检查目录
echo -e "${YELLOW}[1/7] 检查项目目录...${NC}"
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${GREEN}✓ 项目目录存在${NC}"
else
    echo -e "${RED}✗ 项目目录不存在: $PROJECT_DIR${NC}"
    ERRORS=$((ERRORS+1))
fi

# 2. 检查 uv
echo ""
echo -e "${YELLOW}[2/7] 检查 uv...${NC}"
if command -v uv &> /dev/null; then
    echo -e "${GREEN}✓ uv 已安装: $(uv --version)${NC}"
else
    echo -e "${RED}✗ uv 未安装${NC}"
    echo "  安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh"
    ERRORS=$((ERRORS+1))
fi

# 3. 检查虚拟环境
echo ""
echo -e "${YELLOW}[3/7] 检查虚拟环境...${NC}"
if [ -d "$PROJECT_DIR/.venv" ]; then
    echo -e "${GREEN}✓ 虚拟环境存在${NC}"
    
    # 检查 Python
    if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
        echo -e "${GREEN}✓ Python 解释器存在${NC}"
    else
        echo -e "${RED}✗ Python 解释器不存在${NC}"
        ERRORS=$((ERRORS+1))
    fi
else
    echo -e "${RED}✗ 虚拟环境不存在${NC}"
    echo "  创建命令: cd $PROJECT_DIR && uv venv"
    ERRORS=$((ERRORS+1))
fi

# 4. 检查依赖
echo ""
echo -e "${YELLOW}[4/7] 检查依赖...${NC}"
cd "$PROJECT_DIR"

MISSING_DEPS=""
for pkg in redis rq flask gunicorn; do
    if ! .venv/bin/python -c "import $pkg" 2>/dev/null; then
        MISSING_DEPS="$MISSING_DEPS $pkg"
    fi
done

if [ -z "$MISSING_DEPS" ]; then
    echo -e "${GREEN}✓ 所有依赖已安装${NC}"
else
    echo -e "${YELLOW}! 缺少依赖:$MISSING_DEPS${NC}"
    echo "  安装命令: uv pip install$MISSING_DEPS"
fi

# 5. 检查 Redis
echo ""
echo -e "${YELLOW}[5/7] 检查 Redis...${NC}"
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &>/dev/null; then
        echo -e "${GREEN}✓ Redis 运行正常${NC}"
    else
        echo -e "${YELLOW}! Redis 已安装但未运行${NC}"
        echo "  启动命令: sudo systemctl start redis-server"
    fi
else
    echo -e "${YELLOW}! Redis 未安装${NC}"
    echo "  安装命令: sudo apt-get install redis-server"
fi

# 6. 检查脚本
echo ""
echo -e "${YELLOW}[6/7] 检查启动脚本...${NC}"
for script in start_web.sh start_worker.sh; do
    if [ -f "$PROJECT_DIR/scripts/$script" ]; then
        if [ -x "$PROJECT_DIR/scripts/$script" ]; then
            echo -e "${GREEN}✓ $script 存在且可执行${NC}"
        else
            echo -e "${YELLOW}! $script 存在但不可执行${NC}"
            echo "  修复命令: chmod +x scripts/$script"
        fi
    else
        echo -e "${RED}✗ $script 不存在${NC}"
        ERRORS=$((ERRORS+1))
    fi
done

# 7. 检查 systemd 配置
echo ""
echo -e "${YELLOW}[7/7] 检查 systemd 配置...${NC}"
for service in tangdou-mp3.service tangdou-worker.service; do
    if [ -f "$PROJECT_DIR/scripts/$service" ]; then
        echo -e "${GREEN}✓ $service 存在${NC}"
    else
        echo -e "${RED}✗ $service 不存在${NC}"
        ERRORS=$((ERRORS+1))
    fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}  检查通过，可以部署！${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "执行部署:"
    echo "  ./scripts/deploy_redis_queue.sh"
    exit 0
else
    echo -e "${RED}  检查失败，发现 $ERRORS 个问题${NC}"
    echo -e "${BLUE}========================================${NC}"
    exit 1
fi
