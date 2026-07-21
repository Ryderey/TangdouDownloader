"""
Reliable Redis/RQ task processor.

This module keeps Redis as the primary queue/state backend while writing every
task state to local JSON first. The local copy lets the web process answer
status requests during Redis outages and lets workers restore unfinished tasks
after queue loss or worker downtime.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import redis
    from rq import Queue, Retry, Worker
    from rq.exceptions import NoSuchJobError
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    Queue = None
    Retry = None
    Worker = None
    NoSuchJobError = Exception
    REDIS_AVAILABLE = False
    print("[WARNING] Redis/RQ not installed, task submission unavailable")

from modules.downloader import VideoDownloader
from modules.tangdou import get_vid


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "static" / "downloads"
DEFAULT_RETENTION_HOURS = 3

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

TASK_KEY_PREFIX = "tangdou:task:"
TASK_IDS_KEY = "tangdou:task_ids"
DEDUPE_KEY_PREFIX = "tangdou:dedupe:"

UNFINISHED_STATUSES = {
    "pending",
    "queued",
    "info",
    "downloading",
    "download",
    "convert",
    "started",
}
DUPLICATE_STATUSES = UNFINISHED_STATUSES | {"completed"}


class RedisUnavailableError(RuntimeError):
    """Redis is unavailable, so accepting a new task would be unsafe."""


class DuplicateTaskError(RuntimeError):
    """The same vid + audio processing options already has a retained task."""

    def __init__(self, existing_task_id: str, status: str):
        super().__init__("重复任务")
        self.existing_task_id = existing_task_id
        self.status = status


def _decode_redis_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def get_retention_hours() -> int:
    raw = os.environ.get("TANGDOU_RETENTION_HOURS")
    if raw is None:
        return DEFAULT_RETENTION_HOURS
    try:
        return max(int(float(raw)), 1)
    except ValueError:
        return DEFAULT_RETENTION_HOURS


def retention_seconds(hours: Optional[int] = None) -> int:
    return int((hours if hours is not None else get_retention_hours()) * 3600)


def redis_state_ttl_seconds() -> int:
    return max(retention_seconds() + 600, 3600)


def get_redis_connection():
    """Redis connection for task status storage."""
    if not REDIS_AVAILABLE:
        raise RuntimeError("Redis module not installed")
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def get_rq_redis_connection():
    """Redis connection for RQ, which requires raw byte responses."""
    if not REDIS_AVAILABLE:
        raise RuntimeError("Redis module not installed")
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def build_dedupe_key(
    url: str,
    skip_seconds: int,
    trim_end_seconds: int = 3,
    repeat_count: int = 2,
) -> tuple[str, str]:
    vid = get_vid(url)
    if vid is None:
        raise ValueError("Cannot parse vid from URL: {}".format(url))
    payload = (
        f"{vid}:{int(skip_seconds)}:"
        f"{int(trim_end_seconds)}:{int(repeat_count)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), vid


def _normalize_download_dir(download_dir: str | Path = DEFAULT_DOWNLOAD_DIR) -> Path:
    path = Path(download_dir)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


@dataclass
class Task:
    """Task state persisted to Redis and local JSON."""

    id: str
    url: str
    skip_seconds: int = 5
    trim_end_seconds: int = 3
    repeat_count: int = 2
    status: str = "pending"
    progress: int = 0
    message: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    logs: list = field(default_factory=list)
    dedupe_key: str = ""
    rq_job_id: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "skip_seconds": self.skip_seconds,
            "trim_end_seconds": self.trim_end_seconds,
            "repeat_count": self.repeat_count,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "logs": self.logs,
            "dedupe_key": self.dedupe_key,
            "rq_job_id": self.rq_job_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        created_at = data.get("created_at", time.time())
        return cls(
            id=data["id"],
            url=data["url"],
            skip_seconds=data.get("skip_seconds", 5),
            trim_end_seconds=data.get("trim_end_seconds", 0),
            repeat_count=data.get("repeat_count", 1),
            status=data.get("status", "pending"),
            progress=data.get("progress", 0),
            message=data.get("message", ""),
            result=data.get("result", {}),
            error=data.get("error", ""),
            created_at=created_at,
            updated_at=data.get("updated_at", created_at),
            completed_at=data.get("completed_at"),
            logs=data.get("logs", []),
            dedupe_key=data.get("dedupe_key", ""),
            rq_job_id=data.get("rq_job_id"),
        )

    def add_log(self, level: str, message: str):
        self.updated_at = time.time()
        self.logs.append(
            {
                "time": time.strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            }
        )


class TaskStore:
    """Redis-first task store with atomic local JSON fallback."""

    TASK_KEY_PREFIX = TASK_KEY_PREFIX
    TASK_IDS_KEY = TASK_IDS_KEY

    def __init__(self, redis_conn=None, download_dir: str | Path = DEFAULT_DOWNLOAD_DIR):
        self.redis = redis_conn
        if self.redis is None and REDIS_AVAILABLE:
            try:
                self.redis = get_redis_connection()
            except Exception as exc:
                print("[TaskStore] Redis connection init failed: {}".format(exc))
                self.redis = None

        self.data_dir = _normalize_download_dir(download_dir)
        self.tasks_dir = self.data_dir / ".tasks"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _get_task_key(self, task_id: str) -> str:
        return f"{self.TASK_KEY_PREFIX}{task_id}"

    def _get_task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def redis_available(self) -> bool:
        if self.redis is None:
            return False
        try:
            self.redis.ping()
            return True
        except Exception:
            return False

    def _save_local(self, task: Task):
        path = self._get_task_path(task.id)
        tmp_path = self.tasks_dir / f".{task.id}.json.tmp"
        data = json.dumps(task.to_dict(), ensure_ascii=False, indent=2)
        tmp_path.write_text(data, encoding="utf-8")
        os.replace(tmp_path, path)

    def _load_local(self, task_id: str) -> Optional[Task]:
        path = self._get_task_path(task_id)
        if not path.exists():
            return None
        try:
            return Task.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            print("[TaskStore] Failed to load local task {}: {}".format(path, exc))
            return None

    def _iter_local_tasks(self):
        if not self.tasks_dir.exists():
            return
        for path in self.tasks_dir.glob("*.json"):
            try:
                yield Task.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                print("[TaskStore] Skipping corrupted task file {}: {}".format(path, exc))

    def save(self, task: Task):
        """Save locally first, then best-effort to Redis."""
        task.updated_at = time.time()
        self._save_local(task)

        if self.redis is None:
            return
        try:
            key = self._get_task_key(task.id)
            data = json.dumps(task.to_dict(), ensure_ascii=False)
            self.redis.setex(key, redis_state_ttl_seconds(), data)
            self.redis.sadd(self.TASK_IDS_KEY, task.id)
            self.redis.expire(self.TASK_IDS_KEY, redis_state_ttl_seconds())
        except Exception as exc:
            print("[TaskStore] Redis write failed, local state preserved: {}".format(exc))

    def get(self, task_id: str) -> Optional[Task]:
        """Read Redis first, then local JSON."""
        if self.redis is not None:
            try:
                data = self.redis.get(self._get_task_key(task_id))
                if data:
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", errors="ignore")
                    return Task.from_dict(json.loads(data))
            except Exception as exc:
                print("[TaskStore] Redis read failed, falling back to local: {}".format(exc))

        return self._load_local(task_id)

    def get_all_tasks(self, limit: int = 100) -> list:
        tasks_by_id = {task.id: task for task in self._iter_local_tasks()}

        if self.redis is not None:
            try:
                task_ids = self.redis.smembers(self.TASK_IDS_KEY)
                for raw_task_id in task_ids:
                    task_id = str(_decode_redis_value(raw_task_id))
                    task = self.get(task_id)
                    if task:
                        tasks_by_id[task.id] = task
            except Exception as exc:
                print("[TaskStore] Failed to get Redis task list, using local: {}".format(exc))

        tasks = list(tasks_by_id.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def delete(self, task_id: str):
        try:
            self._get_task_path(task_id).unlink(missing_ok=True)
        except Exception as exc:
            print("[TaskStore] Failed to delete local task {}: {}".format(task_id, exc))

        if self.redis is None:
            return
        try:
            self.redis.delete(self._get_task_key(task_id))
            self.redis.srem(self.TASK_IDS_KEY, task_id)
        except Exception as exc:
            print("[TaskStore] Failed to delete Redis task {}: {}".format(task_id, exc))

    def _task_dedupe_key(self, task: Task) -> str:
        if task.dedupe_key:
            return task.dedupe_key
        try:
            dedupe_key, _vid = build_dedupe_key(
                task.url,
                task.skip_seconds,
                task.trim_end_seconds,
                task.repeat_count,
            )
            return dedupe_key
        except Exception:
            return ""

    def find_duplicate(self, dedupe_key: str, max_age_hours: Optional[int] = None) -> Optional[Task]:
        now = time.time()
        max_age = retention_seconds(max_age_hours)
        for task in self.get_all_tasks(limit=10000):
            if self._task_dedupe_key(task) != dedupe_key:
                continue
            if task.status not in DUPLICATE_STATUSES:
                continue
            timestamp = task.completed_at or task.updated_at or task.created_at
            if now - timestamp <= max_age:
                return task
        return None

    def refresh_dedupe(self, task: Task, max_age_hours: Optional[int] = None):
        dedupe_key = self._task_dedupe_key(task)
        if self.redis is None or not dedupe_key:
            return
        try:
            self.redis.setex(
                f"{DEDUPE_KEY_PREFIX}{dedupe_key}",
                retention_seconds(max_age_hours),
                task.id,
            )
        except Exception as exc:
            print("[TaskStore] Failed to refresh dedupe key: {}".format(exc))

    def release_dedupe(self, task: Task):
        dedupe_key = self._task_dedupe_key(task)
        if self.redis is None or not dedupe_key:
            return
        key = f"{DEDUPE_KEY_PREFIX}{dedupe_key}"
        try:
            existing_task_id = _decode_redis_value(self.redis.get(key))
            if existing_task_id == task.id:
                self.redis.delete(key)
        except Exception as exc:
            print("[TaskStore] Failed to release dedupe key: {}".format(exc))

    def get_unfinished_tasks(self) -> list:
        return [
            task
            for task in self.get_all_tasks(limit=10000)
            if task.status in UNFINISHED_STATUSES
        ]

    def _delete_file(self, path: str | Path | None) -> int:
        if not path:
            return 0
        target = Path(path)
        if not target.is_absolute():
            target = BASE_DIR / target
        try:
            if target.exists() and target.is_file():
                target.unlink()
                print("[Cleanup] Deleted file: {}".format(target))
                return 1
        except Exception as exc:
            print("[Cleanup] Failed to delete file {}: {}".format(target, exc))
        return 0

    def _cleanup_orphan_files(
        self,
        cutoff_time: float,
        delete_mp3: bool,
        protected_paths: Optional[set[Path]] = None,
    ) -> int:
        cleaned_count = 0
        protected_paths = protected_paths or set()
        if not self.data_dir.exists():
            return cleaned_count

        suffixes = {".mp4"}
        if delete_mp3:
            suffixes.add(".mp3")

        for path in self.data_dir.rglob("*"):
            if self.tasks_dir in path.parents or not path.is_file():
                continue
            if path.name == ".gitkeep":
                continue
            if path.resolve() in protected_paths:
                continue
            is_part = path.name.endswith(".part")
            if not is_part and path.suffix.lower() not in suffixes:
                continue
            try:
                if path.stat().st_mtime <= cutoff_time:
                    path.unlink()
                    cleaned_count += 1
                    print("[Cleanup] Deleted expired file: {}".format(path))
            except Exception as exc:
                print("[Cleanup] Failed to delete expired file {}: {}".format(path, exc))
        return cleaned_count

    def _cleanup_stale_dedupe_keys(self):
        if self.redis is None:
            return
        try:
            for raw_key in self.redis.scan_iter(f"{DEDUPE_KEY_PREFIX}*"):
                key = _decode_redis_value(raw_key)
                task_id = _decode_redis_value(self.redis.get(key))
                task = self.get(task_id) if task_id else None
                if task is None or task.status == "failed":
                    self.redis.delete(key)
        except Exception as exc:
            print("[Cleanup] Failed to clean dedupe keys: {}".format(exc))

    def cleanup_old(self, max_age_hours: Optional[int] = None, delete_mp3: bool = True) -> int:
        max_age_hours = get_retention_hours() if max_age_hours is None else max_age_hours
        now = time.time()
        cutoff_time = now if max_age_hours == 0 else now - max_age_hours * 3600
        cleaned_count = 0

        for task in self.get_all_tasks(limit=10000):
            timestamp = task.completed_at or task.updated_at or task.created_at
            if max_age_hours != 0 and timestamp > cutoff_time:
                continue

            if delete_mp3 and task.result:
                cleaned_count += self._delete_file(task.result.get("mp3_path"))
                mp3_filename = task.result.get("mp3_filename")
                if mp3_filename:
                    cleaned_count += self._delete_file(self.data_dir / mp3_filename)

            if task.result:
                cleaned_count += self._delete_file(task.result.get("video_path"))

            self.release_dedupe(task)
            self.delete(task.id)
            cleaned_count += 1
            print("[Cleanup] Deleted task: {}".format(task.id))

        protected_paths = set()
        for task in self.get_all_tasks(limit=10000):
            if not task.result:
                continue
            candidates = [task.result.get("mp3_path"), task.result.get("video_path")]
            mp3_filename = task.result.get("mp3_filename")
            if mp3_filename:
                candidates.append(self.data_dir / mp3_filename)
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    protected_paths.add(Path(candidate).resolve())
                except Exception:
                    pass

        cleaned_count += self._cleanup_orphan_files(
            cutoff_time,
            delete_mp3=delete_mp3,
            protected_paths=protected_paths,
        )
        self._cleanup_stale_dedupe_keys()
        return cleaned_count


def process_download_task(
    task_id: str,
    url: str,
    skip_seconds: int,
    trim_end_seconds: int = 0,
    repeat_count: int = 1,
):
    """RQ worker entrypoint."""
    print("[Worker] Processing task: {}".format(task_id))

    store = TaskStore()
    downloader = VideoDownloader()

    task = store.get(task_id)
    if not task:
        dedupe_key = ""
        try:
            dedupe_key, _vid = build_dedupe_key(
                url,
                skip_seconds,
                trim_end_seconds,
                repeat_count,
            )
        except Exception:
            pass
        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds,
            trim_end_seconds=trim_end_seconds,
            repeat_count=repeat_count,
            dedupe_key=dedupe_key,
        )
    elif not task.dedupe_key:
        task.dedupe_key = store._task_dedupe_key(task)

    video_path = None

    try:
        task.status = "downloading"
        task.message = "Downloading video..."
        task.add_log("info", "Start downloading video")
        store.save(task)

        last_update_percent = 0
        last_update_stage = ""

        def progress_callback(stage, percent):
            nonlocal last_update_percent, last_update_stage

            should_update = (
                stage != last_update_stage
                or abs(percent - last_update_percent) >= 10
                or percent == 100
            )

            if should_update:
                task.status = stage
                task.progress = percent
                task.message = _get_status_message(stage)
                task.add_log("info", f"{stage}: {percent}%")
                store.save(task)
                last_update_percent = percent
                last_update_stage = stage

        result = downloader.process_pipeline(
            url,
            skip_seconds=skip_seconds,
            trim_end_seconds=trim_end_seconds,
            repeat_count=repeat_count,
            progress_callback=progress_callback,
        )

        video_path = result.get("video_path")
        if video_path:
            downloader.cleanup(video_path, keep_video=False)

        task.result = result
        task.status = "completed"
        task.progress = 100
        task.message = "Processing complete"
        task.completed_at = time.time()
        task.add_log("success", "Processing complete")
        store.save(task)
        store.refresh_dedupe(task)

        print("[Worker] Task complete: {}".format(task_id))
        return result

    except Exception as exc:
        if video_path:
            try:
                downloader.cleanup(video_path, keep_video=False)
            except Exception:
                pass

        task.status = "failed"
        task.error = str(exc)
        task.message = "Processing failed: {}".format(exc)
        task.completed_at = time.time()
        task.add_log("error", str(exc))
        store.save(task)
        store.release_dedupe(task)

        print("[Worker] Task failed: {}, error: {}".format(task_id, exc))
        raise


def _get_status_message(stage: str) -> str:
    messages = {
        "info": "获取视频信息...",
        "downloading": "正在下载视频...",
        "download": "正在下载视频...",
        "convert": "正在转换为MP3...",
        "complete": "处理完成",
        "completed": "处理完成",
    }
    return messages.get(stage, stage)


def _enqueue_task(queue, task: Task):
    job = queue.enqueue(
        process_download_task,
        task.id,
        task.url,
        task.skip_seconds,
        task.trim_end_seconds,
        task.repeat_count,
        job_id=task.id,
        retry=Retry(max=2),
        job_timeout=900,
    )
    task.rq_job_id = job.id
    return job


def recover_unfinished_tasks(queue=None, redis_conn=None) -> int:
    """Requeue unfinished local tasks when the worker starts."""
    if not REDIS_AVAILABLE:
        print("[Recovery] Redis/RQ not installed, skipping recovery")
        return 0

    redis_conn = redis_conn or get_rq_redis_connection()
    queue = queue or Queue("tangdou", connection=redis_conn)
    store = TaskStore()
    restored = 0

    for task in store.get_unfinished_tasks():
        try:
            job = queue.fetch_job(task.id)
            job_exists = job is not None
        except NoSuchJobError:
            job_exists = False
        except Exception:
            job_exists = False

        if job_exists:
            continue

        if not task.dedupe_key:
            task.dedupe_key = store._task_dedupe_key(task)
        task.status = "queued"
        task.progress = max(task.progress, 0)
        task.message = "Waiting for recovery..."
        task.add_log("info", "Requeued on worker start")
        _enqueue_task(queue, task)
        store.save(task)
        store.refresh_dedupe(task)
        restored += 1
        print("[Recovery] Restored task: {}".format(task.id))

    print("[Recovery] Recovery complete, requeued {} tasks".format(restored))
    return restored


class TaskProcessor:
    """Web-side task manager."""

    def __init__(self, download_dir: str = "static/downloads"):
        self.download_dir = str(_normalize_download_dir(download_dir))
        self._downloader = None
        self.redis_conn = None
        self.rq_redis_conn = None
        self.queue = None

        if REDIS_AVAILABLE:
            self.redis_conn = get_redis_connection()
            self.rq_redis_conn = get_rq_redis_connection()
            self.queue = Queue("tangdou", connection=self.rq_redis_conn)

        self.store = TaskStore(self.redis_conn, self.download_dir)
        print("[TaskProcessor] Queue: tangdou")

    @property
    def downloader(self):
        if self._downloader is None:
            self._downloader = VideoDownloader(self.download_dir)
        return self._downloader

    def redis_available(self) -> bool:
        if not REDIS_AVAILABLE or self.redis_conn is None or self.rq_redis_conn is None:
            return False
        try:
            self.redis_conn.ping()
            self.rq_redis_conn.ping()
            return True
        except Exception:
            return False

    def _reserve_dedupe(self, dedupe_key: str, task_id: str, max_age_hours: int):
        if not self.redis_available():
            raise RedisUnavailableError("Redis unavailable, task not submitted")

        key = "{}{}".format(DEDUPE_KEY_PREFIX, dedupe_key)
        try:
            reserved = self.redis_conn.set(
                key,
                task_id,
                nx=True,
                ex=retention_seconds(max_age_hours),
            )
        except Exception as exc:
            raise RedisUnavailableError("Redis unavailable, task not submitted") from exc

        if reserved:
            return

        try:
            existing_task_id = _decode_redis_value(self.redis_conn.get(key)) or ""
        except Exception as exc:
            raise RedisUnavailableError("Redis unavailable, task not submitted") from exc

        existing_task = self.store.get(str(existing_task_id)) if existing_task_id else None
        if existing_task and existing_task.status not in DUPLICATE_STATUSES:
            try:
                self.redis_conn.delete(key)
                retry_reserved = self.redis_conn.set(
                    key,
                    task_id,
                    nx=True,
                    ex=retention_seconds(max_age_hours),
                )
                if retry_reserved:
                    return
            except Exception as exc:
                raise RedisUnavailableError("Redis unavailable, task not submitted") from exc
        if existing_task:
            raise DuplicateTaskError(existing_task.id, existing_task.status)
        raise DuplicateTaskError(str(existing_task_id), "queued")

    def submit(
        self,
        url: str,
        skip_seconds: int = 5,
        trim_end_seconds: int = 3,
        repeat_count: int = 2,
    ) -> str:
        if not self.redis_available() or self.queue is None:
            raise RedisUnavailableError("Redis unavailable, task not submitted")

        max_age_hours = get_retention_hours()
        dedupe_key, _vid = build_dedupe_key(
            url,
            skip_seconds,
            trim_end_seconds,
            repeat_count,
        )
        duplicate = self.store.find_duplicate(dedupe_key, max_age_hours=max_age_hours)
        if duplicate:
            raise DuplicateTaskError(duplicate.id, duplicate.status)

        task_id = str(uuid.uuid4())[:8]
        self._reserve_dedupe(dedupe_key, task_id, max_age_hours=max_age_hours)

        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds,
            trim_end_seconds=trim_end_seconds,
            repeat_count=repeat_count,
            status="queued",
            message="Waiting...",
            dedupe_key=dedupe_key,
        )
        task.add_log("info", "Task created, added to queue")

        try:
            self.store.save(task)
            job = _enqueue_task(self.queue, task)
            self.store.save(task)
            print("[Task] Submitted: {}, RQ job: {}".format(task_id, job.id))
            return task_id
        except Exception as exc:
            self.store.release_dedupe(task)
            self.store.delete(task.id)
            if REDIS_AVAILABLE and isinstance(exc, redis.RedisError):
                raise RedisUnavailableError("Redis unavailable, task not submitted") from exc
            raise

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.store.get(task_id)

    def get_all_tasks(self, limit: int = 100) -> list:
        return self.store.get_all_tasks(limit)

    def cleanup_old_files(self, max_age_hours: Optional[int] = None) -> int:
        max_age_hours = get_retention_hours() if max_age_hours is None else max_age_hours
        print("[Cleanup] Starting cleanup, retention: {} hours".format(max_age_hours))
        count = self.store.cleanup_old(max_age_hours=max_age_hours, delete_mp3=True)
        print("[Cleanup] Complete, {} files cleaned".format(count))
        return count

    def get_queue_stats(self) -> dict:
        stats = {
            "queued": 0,
            "started": 0,
            "finished": 0,
            "failed": 0,
            "redis_available": False,
            "worker_count": 0,
            "worker_names": [],
            "workers_visible": False,
        }

        if not self.redis_available() or self.queue is None:
            stats["error"] = "Redis不可用"
            return stats

        try:
            workers = Worker.all(connection=self.rq_redis_conn)
            stats.update(
                {
                    "queued": self.queue.count,
                    "started": self.queue.started_job_registry.count,
                    "finished": self.queue.finished_job_registry.count,
                    "failed": self.queue.failed_job_registry.count,
                    "redis_available": True,
                    "worker_count": len(workers),
                    "worker_names": [worker.name for worker in workers],
                    "workers_visible": len(workers) > 0,
                }
            )
        except Exception as exc:
            stats["error"] = str(exc)
        return stats


_processor = None


def get_processor() -> TaskProcessor:
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor


__all__ = [
    "DuplicateTaskError",
    "RedisUnavailableError",
    "Task",
    "TaskProcessor",
    "TaskStore",
    "build_dedupe_key",
    "get_processor",
    "get_retention_hours",
    "get_redis_connection",
    "get_rq_redis_connection",
    "process_download_task",
    "recover_unfinished_tasks",
]
