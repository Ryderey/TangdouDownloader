#!/usr/bin/env python3
"""
RQ Worker 启动脚本 - 使用 Python API 避免 CLI 版本差异。
"""

import logging
import os
import sys
from pathlib import Path


PROJECT_DIR = str(
    Path(os.environ.get("TANGDOU_BASE_DIR") or Path(__file__).resolve().parent.parent).resolve()
)
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
        logger.info("Connected to Redis")

        queue = Queue("tangdou", connection=redis_conn)
        logger.info("Queue: tangdou")

        restored = recover_unfinished_tasks(queue=queue, redis_conn=redis_conn)
        logger.info("Startup recovery complete, requeued %s tasks", restored)

        worker = Worker(
            [queue],
            connection=redis_conn,
            name=f"tangdou-worker-{os.uname().nodename}",
        )
        logger.info("Starting Worker...")
        worker.work(with_scheduler=True, logging_level="INFO")

    except ImportError as exc:
        logger.error("Import failed: %s", exc)
        logger.error("Make sure redis and rq are installed: pip install redis rq")
        return 1
    except Exception as exc:
        logger.error("Error: %s", exc)
        import traceback

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
