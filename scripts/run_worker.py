#!/usr/bin/env python3
"""
Legacy wrapper for the project RQ Worker.

Keep this filename usable for old runbooks while delegating to rq_worker.py,
which uses the RQ Python API and avoids CLI option differences across versions.
"""
import os
import sys
from pathlib import Path

# 添加项目路径
PROJECT_DIR = str(
    Path(os.environ.get("TANGDOU_BASE_DIR") or Path(__file__).resolve().parent.parent).resolve()
)
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from scripts.rq_worker import main


if __name__ == "__main__":
    raise SystemExit(main())
