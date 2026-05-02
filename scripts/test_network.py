#!/usr/bin/env python3
"""
网络诊断脚本 - 检查糖豆视频下载网络问题
测试DNS解析和HTTPS连接
"""

import socket
import ssl
import sys
import subprocess
import time
from urllib.parse import urlparse

# 测试目标
TARGET_DOMAIN = "aqiniushare.tangdou.com"
TARGET_URL = "https://aqiniushare.tangdou.com/"
TEST_DNS_SERVERS = [
    ("系统默认", None),
    ("阿里云DNS", "223.5.5.5"),
    ("阿里云DNS2", "223.6.6.6"),
    ("114DNS", "114.114.114.114"),
    ("腾讯DNS", "119.29.29.29"),
    ("Google DNS", "8.8.8.8"),
]

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*50}{NC}")
    print(f"{BLUE}{text}{NC}")
    print(f"{BLUE}{'='*50}{NC}")

def print_success(text):
    print(f"{GREEN}✓ {text}{NC}")

def print_error(text):
    print(f"{RED}✗ {text}{NC}")

def print_warning(text):
    print(f"{YELLOW}! {text}{NC}")

def print_info(text):
    print(f"{BLUE}{text}{NC}")

def test_dns_resolution(dns_server=None):
    """测试DNS解析"""
    try:
        if dns_server:
            # 使用指定DNS服务器
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [dns_server]
            resolver.timeout = 5
            resolver.lifetime = 5
            answers = resolver.resolve(TARGET_DOMAIN, 'A')
            ips = [str(rdata) for rdata in answers]
            return ips
        else:
            # 使用系统默认DNS
            result = socket.gethostbyname_ex(TARGET_DOMAIN)
            return result[2]
    except Exception as e:
        return f"ERROR: {str(e)}"

def test_tcp_connection(ip, port=443, timeout=10):
    """测试TCP连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception as e:
        return False

def test_https_request(url, timeout=15):
    """测试HTTPS请求"""
    try:
        import urllib.request
        import urllib.error
        
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        # 创建SSL上下文，忽略证书验证（仅用于测试）
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
            return {
                'success': True,
                'status': response.status,
                'headers': dict(response.headers)
            }
    except urllib.error.HTTPError as e:
        return {
            'success': False,
            'error': f"HTTP {e.code}: {e.reason}"
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def test_with_requests():
    """使用requests库测试（如果已安装）"""
    try:
        import requests
        print_info("使用 requests 库测试...")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        response = session.get(TARGET_URL, timeout=15, verify=False)
        return {
            'success': True,
            'status': response.status_code,
            'headers': dict(response.headers)
        }
    except ImportError:
        return {'success': False, 'error': 'requests库未安装'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def check_tailscale():
    """检查Tailscale状态"""
    try:
        result = subprocess.run(['tailscale', 'status'], 
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except:
        return None

def main():
    print_header("糖豆MP3提取器 - 网络诊断工具")
    
    # 1. 测试各种DNS服务器
    print_header("[1] DNS解析测试")
    
    for dns_name, dns_ip in TEST_DNS_SERVERS:
        print_info(f"测试 {dns_name}: {dns_ip or '系统默认'}")
        
        try:
            result = test_dns_resolution(dns_ip)
            if isinstance(result, list) and result:
                print_success(f"解析成功: {', '.join(result)}")
            elif isinstance(result, str) and result.startswith("ERROR"):
                print_error(f"解析失败: {result}")
            else:
                print_error(f"解析失败: 未知错误")
        except Exception as e:
            print_error(f"解析失败: {e}")
    
    # 2. 尝试解析IP后进行TCP连接测试
    print_header("[2] TCP连接测试")
    
    try:
        ips = test_dns_resolution("223.5.5.5")
        if isinstance(ips, list) and ips:
            for ip in ips[:2]:  # 只测试前2个IP
                print_info(f"测试TCP连接到 {ip}:443")
                if test_tcp_connection(ip):
                    print_success(f"TCP连接成功")
                else:
                    print_error(f"TCP连接失败")
        else:
            print_warning("无法获取IP进行TCP测试")
    except Exception as e:
        print_error(f"TCP测试失败: {e}")
    
    # 3. HTTPS请求测试
    print_header("[3] HTTPS请求测试")
    
    print_info("使用 urllib 测试...")
    result = test_https_request(TARGET_URL)
    if result['success']:
        print_success(f"HTTPS请求成功，状态码: {result['status']}")
    else:
        print_error(f"HTTPS请求失败: {result['error']}")
    
    # 尝试使用requests
    print_info("尝试使用 requests 库...")
    result = test_with_requests()
    if result['success']:
        print_success(f"requests请求成功，状态码: {result['status']}")
    else:
        if 'requests库未安装' in result['error']:
            print_warning(result['error'])
        else:
            print_error(f"requests请求失败: {result['error']}")
    
    # 4. 检查Tailscale
    print_header("[4] Tailscale状态")
    tailscale_status = check_tailscale()
    if tailscale_status:
        print_info("Tailscale已连接:")
        print(tailscale_status[:500])
    else:
        print_warning("Tailscale未运行或未安装")
    
    # 5. 系统DNS配置
    print_header("[5] 系统DNS配置")
    try:
        with open('/etc/resolv.conf', 'r') as f:
            content = f.read()
            print_info("/etc/resolv.conf 内容:")
            for line in content.strip().split('\n')[:10]:
                if line.strip() and not line.startswith('#'):
                    print(f"  {line}")
    except Exception as e:
        print_error(f"无法读取DNS配置: {e}")
    
    # 6. 修复建议
    print_header("修复建议")
    print("""
如果DNS解析失败，尝试以下方法：

1. 重启DNS服务:
   sudo systemctl restart systemd-resolved
   
2. 使用公共DNS（临时方案）:
   sudo mv /etc/resolv.conf /etc/resolv.conf.backup
   echo "nameserver 223.5.5.5" | sudo tee /etc/resolv.conf
   echo "nameserver 114.114.114.114" | sudo tee -a /etc/resolv.conf
   
3. 如果是Tailscale导致的DNS问题:
   sudo tailscale up --accept-dns=false
   
4. 检查是否有其他程序占用了DNS:
   sudo lsof -i :53
   
5. 测试直接使用IP访问（绕过DNS）:
   先在其他机器上解析域名得到IP，然后修改/etc/hosts
   echo "<IP地址> aqiniushare.tangdou.com" | sudo tee -a /etc/hosts
""")

if __name__ == "__main__":
    main()
