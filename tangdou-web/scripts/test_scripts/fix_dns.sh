#!/bin/bash
# DNS问题快速修复脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   DNS问题快速修复工具${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查是否root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 备份当前配置
echo -e "${YELLOW}[1/5] 备份当前DNS配置...${NC}"
cp /etc/resolv.conf /etc/resolv.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# 停止 systemd-resolved
echo -e "${YELLOW}[2/5] 重启DNS服务...${NC}"
systemctl restart systemd-resolved 2>/dev/null || true
sleep 1

# 设置公共DNS
echo -e "${YELLOW}[3/5] 配置公共DNS服务器...${NC}"
cat > /etc/resolv.conf << 'EOF'
# 由修复脚本生成
nameserver 223.5.5.5
nameserver 223.6.6.6
nameserver 114.114.114.114
nameserver 8.8.8.8
EOF

# 防止被覆盖
chattr +i /etc/resolv.conf 2>/dev/null || echo -e "${YELLOW}警告: 无法设置immutable属性，配置可能在重启后被覆盖${NC}"

# 测试DNS
echo -e "${YELLOW}[4/5] 测试DNS解析...${NC}"
if nslookup aqiniushare.tangdou.com > /dev/null 2>&1; then
    echo -e "${GREEN}✓ DNS解析正常${NC}"
    nslookup aqiniushare.tangdou.com | grep -A1 "Name:"
else
    echo -e "${RED}✗ DNS解析仍然失败${NC}"
    echo "尝试其他修复方案..."
    
    # 检查是否被防火墙拦截
    echo -e "${BLUE}检查防火墙...${NC}"
    iptables -L -n | grep 53 || true
    
    # 检查是否有本地DNS服务冲突
    echo -e "${BLUE}检查53端口占用...${NC}"
    ss -tlnp | grep :53 || true
fi

# 永久修复方案
echo -e "${YELLOW}[5/5] 应用永久修复...${NC}"

# 禁用Tailscale的DNS覆盖（如果使用Tailscale）
if command -v tailscale &> /dev/null; then
    echo -e "${BLUE}检测到Tailscale，禁用DNS覆盖...${NC}"
    tailscale up --accept-dns=false 2>/dev/null || true
fi

# 配置systemd-resolved使用固定DNS
cat > /etc/systemd/resolved.conf << 'EOF'
[Resolve]
DNS=223.5.5.5 223.6.6.6 114.114.114.114
FallbackDNS=8.8.8.8
DNSStubListener=yes
EOF

systemctl restart systemd-resolved

# 重新创建正确的软链接
rm -f /etc/resolv.conf
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   DNS修复完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "当前DNS配置:"
cat /etc/resolv.conf | grep nameserver | head -5
echo ""
echo "测试命令:"
echo "  nslookup aqiniushare.tangdou.com"
echo "  curl -I https://aqiniushare.tangdou.com/"
