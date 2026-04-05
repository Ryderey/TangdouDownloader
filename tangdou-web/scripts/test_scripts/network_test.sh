#!/bin/bash
# 网络诊断脚本 - 检查糖豆视频下载网络问题
# 适用于 Ubuntu/Debian 系统

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 目标域名
TARGET_DOMAIN="aqiniushare.tangdou.com"
TARGET_URL="https://aqiniushare.tangdou.com/"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   糖豆MP3提取器 - 网络诊断工具${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 检查基础网络连接
echo -e "${YELLOW}[1/8] 检查基础网络连接...${NC}"
if ping -c 2 223.5.5.5 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 公网连接正常 (阿里云DNS)${NC}"
else
    echo -e "${RED}✗ 公网连接失败 - 请检查网络连接${NC}"
fi

# 2. 检查DNS配置
echo ""
echo -e "${YELLOW}[2/8] 检查DNS配置...${NC}"
echo -e "${BLUE}当前DNS服务器:${NC}"
cat /etc/resolv.conf | grep nameserver | head -5

# 3. 测试域名解析 - 使用不同方法
echo ""
echo -e "${YELLOW}[3/8] 测试域名解析: $TARGET_DOMAIN${NC}"

echo -e "${BLUE}方法1: 系统默认DNS解析${NC}"
if host $TARGET_DOMAIN > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 解析成功:${NC}"
    host $TARGET_DOMAIN | head -3
else
    echo -e "${RED}✗ 系统默认DNS解析失败${NC}"
fi

echo ""
echo -e "${BLUE}方法2: 使用114DNS解析${NC}"
if nslookup $TARGET_DOMAIN 114.114.114.114 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 114DNS解析成功${NC}"
    nslookup $TARGET_DOMAIN 114.114.114.114 | grep -A2 "Name:"
else
    echo -e "${RED}✗ 114DNS解析失败${NC}"
fi

echo ""
echo -e "${BLUE}方法3: 使用阿里云DNS解析${NC}"
if nslookup $TARGET_DOMAIN 223.5.5.5 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 阿里云DNS解析成功${NC}"
    nslookup $TARGET_DOMAIN 223.5.5.5 | grep -A2 "Name:"
else
    echo -e "${RED}✗ 阿里云DNS解析失败${NC}"
fi

# 4. 检查Tailscale连接
echo ""
echo -e "${YELLOW}[4/8] 检查Tailscale网络...${NC}"
if command -v tailscale &> /dev/null; then
    echo -e "${BLUE}Tailscale状态:${NC}"
    tailscale status | head -5 || echo -e "${RED}Tailscale未运行或未配置${NC}"
    
    echo ""
    echo -e "${BLUE}本机Tailscale IP:${NC}"
    tailscale ip -4 2>/dev/null || echo -e "${RED}无法获取Tailscale IP${NC}"
else
    echo -e "${YELLOW}! Tailscale未安装${NC}"
fi

# 5. 测试HTTP连接
echo ""
echo -e "${YELLOW}[5/8] 测试HTTPS连接...${NC}"

echo -e "${BLUE}测试访问: $TARGET_URL${NC}"
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$TARGET_URL" 2>&1 || echo "000")
    if [ "$HTTP_CODE" = "000" ]; then
        echo -e "${RED}✗ 连接失败 (可能是DNS或网络问题)${NC}"
    elif [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        echo -e "${GREEN}✓ HTTP连接正常 (状态码: $HTTP_CODE)${NC}"
    else
        echo -e "${YELLOW}! HTTP返回状态码: $HTTP_CODE${NC}"
    fi
else
    echo -e "${YELLOW}! curl未安装${NC}"
fi

# 6. 检查防火墙
echo ""
echo -e "${YELLOW}[6/8] 检查防火墙状态...${NC}"
if command -v ufw &> /dev/null; then
    echo -e "${BLUE}UFW防火墙状态:${NC}"
    sudo ufw status | head -10 || echo -e "${YELLOW}无法获取UFW状态${NC}"
else
    echo -e "${BLUE}UFW未安装${NC}"
fi

# 7. 测试其他糖豆域名
echo ""
echo -e "${YELLOW}[7/8] 测试其他糖豆相关域名...${NC}"
DOMAINS=("www.tangdou.com" "api.tangdou.com" "www.tangdoudn.com")
for domain in "${DOMAINS[@]}"; do
    if nslookup $domain > /dev/null 2>&1; then
        IP=$(nslookup $domain 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)
        echo -e "${GREEN}✓ $domain -> $IP${NC}"
    else
        echo -e "${RED}✗ $domain 解析失败${NC}"
    fi
done

# 8. 检查系统DNS缓存和服务
echo ""
echo -e "${YELLOW}[8/8] 检查DNS相关服务...${NC}"

# 检查 systemd-resolved
if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
    echo -e "${BLUE}systemd-resolved 状态:${NC}"
    systemctl status systemd-resolved --no-pager -l | head -5
    echo ""
    echo -e "${BLUE}当前DNS配置 (resolvectl):${NC}"
    resolvectl status | head -20 || true
else
    echo -e "${BLUE}systemd-resolved 未运行${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}诊断建议:${NC}"
echo ""
echo -e "1. 如果是DNS解析问题，尝试以下修复方法："
echo -e "   ${GREEN}sudo systemctl restart systemd-resolved${NC}"
echo -e "   ${GREEN}sudo rm -f /etc/resolv.conf && sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf${NC}"
echo ""
echo -e "2. 或者临时修改 /etc/resolv.conf 使用公共DNS："
echo -e "   ${GREEN}echo 'nameserver 223.5.5.5' | sudo tee /etc/resolv.conf${NC}"
echo -e "   ${GREEN}echo 'nameserver 114.114.114.114' | sudo tee -a /etc/resolv.conf${NC}"
echo ""
echo -e "3. 如果是Tailscale DNS覆盖问题："
echo -e "   ${GREEN}sudo tailscale up --accept-dns=false${NC}"
echo ""
echo -e "4. 检查是否开启了代理/VPN影响DNS："
echo -e "   ${GREEN}env | grep -i proxy${NC}"
echo ""
echo -e "${BLUE}========================================${NC}"
