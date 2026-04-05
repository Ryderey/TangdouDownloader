#!/usr/bin/env python3
"""
RQ Worker 启动脚本 - 使用 Python API 避免 CLI 版本差异
"""
import sys
import os
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
PROJECT_DIR = "/home/ryl/script/tangdou-web"
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

try:
    import redis
    from rq import Queue
    from rq.worker import SimpleWorker
    from rq.job import Job
    
    # 连接 Redis - 注意：RQ需要禁用decode_responses
    redis_conn = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=int(os.environ.get('REDIS_DB', 0)),
        password=os.environ.get('REDIS_PASSWORD', None),
        decode_responses=False,  # RQ需要原始字节数据
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    
    # 测试连接
    redis_conn.ping()
    logger.info(f"已连接到 Redis")
    
    # 创建队列
    queue = Queue('tangdou', connection=redis_conn)
    logger.info(f"队列: tangdou")
    
    # 启动 Worker
    logger.info("启动 Worker...")
    worker = SimpleWorker(
        [queue],
        connection=redis_conn,
        name='tangdou-worker'
    )
    
    # 开始工作
    worker.work()
    
except ImportError as e:
    logger.error(f"导入失败: {e}")
    logger.error("请确保已安装 redis 和 rq: uv pip install redis rq")
    sys.exit(1)
except Exception as e:
    logger.error(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)