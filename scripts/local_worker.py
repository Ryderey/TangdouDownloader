#!/usr/bin/env python3
"""
Local directory polling worker for no-Redis deployments (Windows 7 compatible).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def resolve_project_dir() -> Path:
    env_dir = os.environ.get("TANGDOU_BASE_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = resolve_project_dir()
os.chdir(str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    backend = os.environ.get("TANGDOU_QUEUE_BACKEND", "local").strip().lower()
    if backend not in {"local", "file", "no_redis", "no-redis"}:
        logger.error("local_worker.py 只能用于本地队列后端，当前: %s", backend)
        return 2

    try:
        from tasks.local_processor import LocalQueueWorker

        worker = LocalQueueWorker()
        logger.info("项目目录: %s", PROJECT_DIR)
        logger.info("本地队列 worker 启动: %s", worker.worker_id)
        worker.run_forever()
    except KeyboardInterrupt:
        logger.info("收到停止信号，worker 退出")
        return 0
    except Exception as exc:
        logger.error("worker 启动失败: %s", exc)
        import traceback

        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
