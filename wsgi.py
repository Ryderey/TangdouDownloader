"""
WSGI 入口文件 - 用于生产部署 (Windows 7 兼容，使用 waitress)
"""
from __future__ import annotations

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app


def main():
    """使用 waitress 启动生产服务"""
    from waitress import serve

    host = os.environ.get("TANGDOU_HOST", "0.0.0.0")
    port = int(os.environ.get("TANGDOU_PORT", 18080))
    threads = int(os.environ.get("TANGDOU_THREADS", 4))

    print("[waitress] 启动服务: http://{}:{}".format(host, port))
    print("[waitress] 工作线程数: {}".format(threads))
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
