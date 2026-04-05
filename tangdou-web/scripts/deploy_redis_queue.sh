#!/bin/bash
# Redis + RQ 部署脚本
# 用于将项目从文件队列迁移到Redis队列

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/home/ryl/script/tangdou-web"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  部署 Redis + RQ 任务队列${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 检查Redis安装
echo -e "${YELLOW}[1/6] 检查Redis安装...${NC}"
if command -v redis-cli &> /dev/null; then
    echo -e "${GREEN}✓ Redis已安装${NC}"
    redis-cli ping || echo -e "${RED}✗ Redis服务未运行${NC}"
else
    echo -e "${YELLOW}! Redis未安装，开始安装...${NC}"
    sudo apt-get update
    sudo apt-get install -y redis-server
    sudo systemctl enable redis-server
    sudo systemctl start redis-server
    echo -e "${GREEN}✓ Redis安装完成${NC}"
fi

# 2. 停止现有服务
echo ""
echo -e "${YELLOW}[2/6] 停止现有服务...${NC}"
systemctl --user stop tangdou-mp3 2>/dev/null || true
systemctl --user stop tangdou-worker 2>/dev/null || true
sleep 2
echo -e "${GREEN}✓ 服务已停止${NC}"

# 3. 安装Python依赖
echo ""
echo -e "${YELLOW}[3/6] 安装Python依赖...${NC}"
cd "$PROJECT_DIR"

# 检查虚拟环境
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo -e "${RED}✗ 未找到虚拟环境 (.venv)${NC}"
    echo "请先创建虚拟环境: uv venv"
    exit 1
fi

# 检测并使用 uv
if command -v uv &> /dev/null; then
    echo "使用 uv 安装依赖..."
    uv pip install redis rq
else
    echo -e "${YELLOW}! 未找到 uv，尝试使用虚拟环境 pip${NC}"
    "$PROJECT_DIR/.venv/bin/pip" install redis rq
fi

echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 4. 清理旧的任务文件（可选）
echo ""
echo -e "${YELLOW}[4/6] 清理旧任务文件...${NC}"
if [ -d "$PROJECT_DIR/static/downloads/.tasks" ]; then
    echo "发现旧的任务文件目录"
    read -p "是否删除旧任务文件? (y/N): " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        rm -rf "$PROJECT_DIR/static/downloads/.tasks"
        echo -e "${GREEN}✓ 旧任务文件已清理${NC}"
    else
        echo "保留旧任务文件"
    fi
else
    echo "无旧任务文件需要清理"
fi

# 5. 安装systemd服务
echo ""
echo -e "${YELLOW}[5/6] 安装systemd服务...${NC}"

# 给启动脚本添加执行权限
chmod +x "$PROJECT_DIR/scripts/start_web.sh"
chmod +x "$PROJECT_DIR/scripts/start_worker.sh"

# 主服务
cp "$PROJECT_DIR/scripts/tangdou-mp3.service" "$HOME/.config/systemd/user/"
# Worker服务
cp "$PROJECT_DIR/scripts/tangdou-worker.service" "$HOME/.config/systemd/user/"

systemctl --user daemon-reload
echo -e "${GREEN}✓ 服务配置已安装${NC}"

# 6. 启动服务
echo ""
echo -e "${YELLOW}[6/6] 启动服务...${NC}"
systemctl --user start tangdou-mp3
systemctl --user start tangdou-worker

sleep 2

# 检查状态
if systemctl --user is-active --quiet tangdou-mp3; then
    echo -e "${GREEN}✓ Web服务运行正常${NC}"
else
    echo -e "${RED}✗ Web服务启动失败${NC}"
    systemctl --user status tangdou-mp3 --no-pager
fi

if systemctl --user is-active --quiet tangdou-worker; then
    echo -e "${GREEN}✓ Worker服务运行正常${NC}"
else
    echo -e "${RED}✗ Worker服务启动失败${NC}"
    systemctl --user status tangdou-worker --no-pager
fi

# 启用开机自启
systemctl --user enable tangdou-mp3
systemctl --user enable tangdou-worker

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "服务状态:"
echo "  Web:   systemctl --user status tangdou-mp3"
echo "  Worker: systemctl --user status tangdou-worker"
echo ""
echo "查看日志:"
echo "  Web:   journalctl --user -u tangdou-mp3 -f"
echo "  Worker: journalctl --user -u tangdou-worker -f"
echo ""
echo "队列状态:"
echo "  curl http://localhost:18080/api/queue-stats"
echo ""
