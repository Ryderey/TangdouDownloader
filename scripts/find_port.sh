#!/bin/bash
# 查找服务实际监听端口

echo "=========================================="
echo "  查找服务实际监听端口"
echo "=========================================="
echo ""

# 方法1: 检查所有python相关进程的网络连接
echo "[1] Python进程的网络连接:"
ss -tlnp | grep -E "(python|gunicorn)" || echo "  未找到"
echo ""

# 方法2: 检查所有监听端口
echo "[2] 所有监听端口 (排除常见系统端口):"
ss -tlnp | grep LISTEN | grep -vE ":(22|53|80|443|3306|6379|8080|8443)" | head -20
echo ""

# 方法3: 通过进程名找端口
echo "[3] 查找 gunicorn/python 端口:"
for pid in $(pgrep -f "(gunicorn|python.*app)" | head -5); do
    echo "PID $pid:"
    ss -tlnp | grep "pid=$pid," || echo "  无监听"
done
echo ""

# 方法4: 检查服务配置
echo "[4] 检查服务配置文件:"
if [ -f ~/.config/systemd/user/tangdou-mp3.service ]; then
    echo "找到用户服务配置:"
    grep -E "(ExecStart|BindToDevice|ListenStream)" ~/.config/systemd/user/tangdou-mp3.service 2>/dev/null
fi

if [ -f /etc/systemd/user/tangdou-mp3.service ]; then
    echo "找到系统用户服务配置:"
    grep -E "(ExecStart|BindToDevice|ListenStream)" /etc/systemd/user/tangdou-mp3.service 2>/dev/null
fi

# 方法5: 检查start脚本
echo ""
echo "[5] 检查启动脚本:"
if [ -f /home/ryl/tangdou-mp3/start.sh ]; then
    echo "找到 start.sh:"
    grep -E "(gunicorn|python|port|bind|5000|8000|8080)" /home/ryl/tangdou-mp3/start.sh | head -5
elif [ -f /home/ryl/script/tangdou-web/start.sh ]; then
    echo "找到 start.sh:"
    grep -E "(gunicorn|python|port|bind|5000|8000|8080)" /home/ryl/script/tangdou-web/start.sh | head -5
fi
echo ""

# 方法6: 直接测试常见端口
echo "[6] 测试常见端口响应:"
for port in 8000 8080 5000 8001 8081 9000; do
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/ 2>/dev/null || echo "000")
    if [ "$response" != "000" ] && [ "$response" != "" ]; then
        echo "  端口 $port: HTTP $response (可用!)"
    fi
done
echo ""

echo "=========================================="
echo "使用方法:"
echo "=========================================="
echo "找到端口后，使用正确的端口访问API:"
echo "  curl -X POST http://localhost:实际端口/api/cleanup"
echo ""
echo "或者检查是否通过Tailscale访问:"
echo "  curl -X POST http://100.99.106.60:实际端口/api/cleanup"
echo ""
