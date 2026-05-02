#!/usr/bin/env python3
"""
RQ Worker 启动脚本 - 使用 Python API 避免 CLI 版本差异。
"""

import logging
import os
import sys


PROJECT_DIR = "/home/ryl/script/tangdou-web"
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    try:
        from rq import Queue, Worker

        from tasks.processor import get_rq_redis_connection, recover_unfinished_tasks

        redis_conn = get_rq_redis_connection()
        redis_conn.ping()
        logger.info("已连接到 Redis")

        queue = Queue("tangdou", connection=redis_conn)
        logger.info("队列: tangdou")

        restored = recover_unfinished_tasks(queue=queue, redis_conn=redis_conn)
        logger.info("启动恢复完成，重新入队 %s 个任务", restored)

        worker = Worker(
            [queue],
            connection=redis_conn,
            name=f"tangdou-worker-{os.uname().nodename}",
        )
        logger.info("启动 Worker...")
        worker.work(with_scheduler=True, logging_level="INFO")

    except ImportError as exc:
        logger.error("导入失败: %s", exc)
        logger.error("请确保已安装 redis 和 rq: uv pip install redis rq")
        return 1
    except Exception as exc:
        logger.error("错误: %s", exc)
        import traceback

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
