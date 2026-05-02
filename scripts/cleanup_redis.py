#!/usr/bin/env python3
"""
Tangdou Redis maintenance helper.

The script is dry-run by default. Pass --yes to actually delete keys.
"""

import argparse
import json
import os
from pathlib import Path

import redis


PROJECT_DIR = Path(__file__).resolve().parent.parent
TASK_KEY_PREFIX = "tangdou:task:"
TASK_IDS_KEY = "tangdou:task_ids"
DEDUPE_KEY_PREFIX = "tangdou:dedupe:"
DEFAULT_QUEUE = os.environ.get("TANGDOU_QUEUE", "tangdou")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

RQ_REGISTRIES = (
    "started",
    "finished",
    "failed",
    "deferred",
    "scheduled",
    "canceled",
)

DUPLICATE_STATUSES = {
    "pending",
    "queued",
    "info",
    "downloading",
    "download",
    "convert",
    "started",
    "completed",
}


def decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def get_connection():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def scan_keys(conn, pattern):
    return sorted(decode(key) for key in conn.scan_iter(pattern))


def existing_keys(conn, keys):
    return [key for key in keys if conn.exists(key)]


def members_for_key(conn, key):
    key_type = decode(conn.type(key))
    if key_type == "list":
        return [decode(item) for item in conn.lrange(key, 0, -1)]
    if key_type == "set":
        return [decode(item) for item in conn.smembers(key)]
    if key_type == "zset":
        return [decode(item) for item in conn.zrange(key, 0, -1)]
    return []


def load_task(conn, task_id):
    if not task_id:
        return None

    raw_data = conn.get(f"{TASK_KEY_PREFIX}{task_id}")
    if raw_data:
        try:
            return json.loads(decode(raw_data))
        except json.JSONDecodeError:
            pass

    local_path = PROJECT_DIR / "static" / "downloads" / ".tasks" / f"{task_id}.json"
    if local_path.exists():
        try:
            return json.loads(local_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def collect_state_keys(conn):
    keys = scan_keys(conn, f"{TASK_KEY_PREFIX}*")
    if conn.exists(TASK_IDS_KEY):
        keys.append(TASK_IDS_KEY)
    return sorted(set(keys))


def collect_dedupe_keys(conn):
    return scan_keys(conn, f"{DEDUPE_KEY_PREFIX}*")


def collect_stale_dedupe_keys(conn):
    stale_keys = []
    for key in collect_dedupe_keys(conn):
        task_id = decode(conn.get(key))
        task = load_task(conn, task_id)
        if task is None or task.get("status") not in DUPLICATE_STATUSES:
            stale_keys.append(key)
    return stale_keys


def collect_task_dedupe_keys(conn, task_id):
    task = load_task(conn, task_id)
    keys = []
    if task and task.get("dedupe_key"):
        keys.append(f"{DEDUPE_KEY_PREFIX}{task['dedupe_key']}")

    for key in collect_dedupe_keys(conn):
        if decode(conn.get(key)) == task_id:
            keys.append(key)
    return existing_keys(conn, sorted(set(keys)))


def collect_rq_keys(conn, queue):
    queue_keys = [f"rq:queue:{queue}"]
    registry_keys = [f"rq:{registry}:{queue}" for registry in RQ_REGISTRIES]
    rq_keys = existing_keys(conn, queue_keys + registry_keys)

    job_ids = set()
    for key in rq_keys:
        job_ids.update(members_for_key(conn, key))

    job_keys = []
    for job_id in sorted(job_ids):
        candidates = (
            f"rq:job:{job_id}",
            f"rq:results:{job_id}",
            f"rq:job:{job_id}:dependents",
            f"rq:job:{job_id}:dependencies",
        )
        job_keys.extend(existing_keys(conn, candidates))

    return sorted(set(rq_keys + job_keys)), sorted(job_ids)


def print_key_list(label, keys):
    print(f"[{label}] {len(keys)} key(s)")
    for key in keys[:50]:
        print(f"  {key}")
    if len(keys) > 50:
        print(f"  ... 还有 {len(keys) - 50} 个 key 未显示")


def delete_keys(conn, keys, yes):
    keys = sorted(set(keys))
    if not keys:
        print("没有需要删除的 Redis key")
        return 0

    if not yes:
        print("未传 --yes，本次仅演练，不删除任何 Redis key")
        return 0

    deleted = 0
    for index in range(0, len(keys), 500):
        deleted += conn.delete(*keys[index:index + 500])
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Clean Tangdou Redis state safely")
    parser.add_argument("--queue", default=DEFAULT_QUEUE, help="RQ queue name, default: tangdou")
    parser.add_argument("--state", action="store_true", help="清理 tangdou:task:* 和 tangdou:task_ids")
    parser.add_argument("--dedupe", action="store_true", help="清理所有 tangdou:dedupe:* 去重键")
    parser.add_argument("--stale-dedupe", action="store_true", help="只清理失效去重键")
    parser.add_argument("--release-task", help="只释放指定 task_id 对应的去重键")
    parser.add_argument("--rq", action="store_true", help="清理 tangdou RQ 队列、注册表和引用到的 job")
    parser.add_argument("--all", action="store_true", help="清理 state、dedupe 和 RQ 队列")
    parser.add_argument("--yes", action="store_true", help="确认执行删除；未提供时只打印将删除的 key")
    args = parser.parse_args()

    if args.all:
        args.state = True
        args.dedupe = True
        args.rq = True

    if not any((args.state, args.dedupe, args.stale_dedupe, args.release_task, args.rq)):
        parser.print_help()
        return 0

    conn = get_connection()
    conn.ping()

    keys_to_delete = []

    if args.state:
        keys = collect_state_keys(conn)
        print_key_list("task state", keys)
        keys_to_delete.extend(keys)

    if args.dedupe:
        keys = collect_dedupe_keys(conn)
        print_key_list("dedupe", keys)
        keys_to_delete.extend(keys)

    if args.stale_dedupe:
        keys = collect_stale_dedupe_keys(conn)
        print_key_list("stale dedupe", keys)
        keys_to_delete.extend(keys)

    if args.release_task:
        keys = collect_task_dedupe_keys(conn, args.release_task)
        print_key_list(f"dedupe for task {args.release_task}", keys)
        keys_to_delete.extend(keys)

    rq_queue_member_removed = False
    if args.rq:
        keys, job_ids = collect_rq_keys(conn, args.queue)
        print_key_list(f"RQ queue {args.queue}", keys)
        print(f"[RQ queue {args.queue}] referenced job(s): {len(job_ids)}")
        keys_to_delete.extend(keys)
        rq_queue_member_removed = conn.sismember("rq:queues", args.queue)
        if rq_queue_member_removed:
            print("  rq:queues member:", args.queue)

    deleted = delete_keys(conn, keys_to_delete, args.yes)

    if args.yes and args.rq and rq_queue_member_removed:
        conn.srem("rq:queues", args.queue)
        print(f"已从 rq:queues 移除队列: {args.queue}")

    if args.yes:
        print(f"已删除 {deleted} 个 Redis key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
