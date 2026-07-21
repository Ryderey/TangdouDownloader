#!/usr/bin/env python3
"""
清理过期任务状态和生成文件。
默认保留 TANGDOU_RETENTION_HOURS（未设置时为 3 小时）。
"""

import argparse
import os
import sys
from pathlib import Path


PROJECT_DIR = str(
    Path(os.environ.get("TANGDOU_BASE_DIR") or Path(__file__).resolve().parent.parent).resolve()
)
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from tasks.processor import TaskStore, get_retention_hours  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup Tangdou generated files and task state")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=get_retention_hours(),
        help="保留小时数，0 表示清理所有历史文件",
    )
    parser.add_argument(
        "--keep-mp3",
        action="store_true",
        help="只清理任务状态和临时文件，保留 MP3",
    )
    args = parser.parse_args()

    store = TaskStore()
    cleaned = store.cleanup_old(max_age_hours=args.max_age_hours, delete_mp3=not args.keep_mp3)
    print(f"[Cleanup] 完成，共清理 {cleaned} 个项目，保留时间 {args.max_age_hours} 小时")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
