#!/usr/bin/env python3
"""
RQ Worker 启动脚本
"""
import sys
import os

# 添加项目路径
PROJECT_DIR = "/home/ryl/script/tangdou-web"
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from rq.cli import main

# 设置参数
# 注意：队列名 tangdou 是位置参数，放在最后
sys.argv = [
    'rq',
    'worker',
    '--name', 'tangdou-worker',
    '--url', 'redis://localhost:6379/0',
    '--with-scheduler',
    '--results-ttl', '604800',
    '--job-ttl', '3600',
    '--logging-level', 'INFO',
    'tangdou'  # 队列名作为位置参数
]

if __name__ == '__main__':
    main()
