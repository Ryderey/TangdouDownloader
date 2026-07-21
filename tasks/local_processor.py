"""
No-Redis task processor backed by local JSON files and a directory polling queue.

This backend is intended for small single-node servers (e.g. Windows 7).
The web process only writes task metadata and queue files; a separate
local_worker.py process claims and executes one job at a time.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Set

from modules.downloader import VideoDownloader
from modules.tangdou import get_vid


BASE_DIR = Path(
    os.environ.get("TANGDOU_BASE_DIR")
    or Path(__file__).resolve().parent.parent
).resolve()
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "static" / "downloads"
DEFAULT_RETENTION_HOURS = 3

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
    """Compatibility exception; the local backend does not require Redis."""


class DuplicateTaskError(RuntimeError):
    """The same vid + audio processing options already has a retained task."""

    def __init__(self, existing_task_id: str, status: str):
        super().__init__("Duplicate task")
        self.existing_task_id = existing_task_id
        self.status = status


# ============ Cross-platform File Lock ============

class FileLock:
    """Cross-platform file lock (msvcrt on Windows, fcntl on Unix)."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        if sys.platform == "win32":
            import msvcrt
            # Lock the first byte; retry until acquired
            while True:
                try:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except (IOError, OSError):
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None:
            if sys.platform == "win32":
                import msvcrt
                try:
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                except (IOError, OSError):
                    pass
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


# ============ Utilities ============

class TTLCache:
    """Tiny in-process LRU cache for frequently read task metadata."""

    def __init__(self, max_size: int = 256, ttl_seconds: float = 2.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict = OrderedDict()

    def get(self, key: str):
        item = self._items.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value):
        self._items[key] = (time.time() + self.ttl_seconds, value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def delete(self, key: str):
        self._items.pop(key, None)


def _normalize_download_dir(download_dir=None) -> Path:
    raw = download_dir or os.environ.get("TANGDOU_DOWNLOAD_DIR") or DEFAULT_DOWNLOAD_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _atomic_write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(
        ".{}.{}.{}.tmp".format(path.name, os.getpid(), int(time.time() * 1000))
    )
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(path))


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


def build_dedupe_key(
    url: str,
    skip_seconds: int,
    trim_end_seconds: int = 3,
    repeat_count: int = 2,
) -> Tuple[str, str]:
    vid = get_vid(url)
    if vid is None:
        raise ValueError("Cannot parse vid from URL: {}".format(url))
    payload = "{}:{}:{}:{}".format(
        vid, int(skip_seconds), int(trim_end_seconds), int(repeat_count)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), vid


# ============ Task Dataclass ============

@dataclass
class Task:
    """Task state persisted as JSON."""

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
            trim_end_seconds=data.get("trim_end_seconds", 3),
            repeat_count=data.get("repeat_count", 2),
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
        if len(self.logs) > 80:
            self.logs = self.logs[-80:]


# ============ Task Store ============

class TaskStore:
    """Local JSON task store."""

    def __init__(self, redis_conn=None, download_dir=None):
        self.redis = None
        self.data_dir = _normalize_download_dir(download_dir)
        self.tasks_dir = self.data_dir / ".tasks"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.cache = TTLCache()

    def _get_task_path(self, task_id: str) -> Path:
        return self.tasks_dir / "{}.json".format(task_id)

    def redis_available(self) -> bool:
        return False

    def _save_local(self, task: Task):
        task.updated_at = time.time()
        _atomic_write_json(self._get_task_path(task.id), task.to_dict())
        self.cache.set(task.id, task)

    def _load_local(self, task_id: str) -> Optional[Task]:
        cached = self.cache.get(task_id)
        if cached is not None:
            return cached
        path = self._get_task_path(task_id)
        if not path.exists():
            return None
        try:
            task = Task.from_dict(json.loads(path.read_text(encoding="utf-8")))
            self.cache.set(task_id, task)
            return task
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
        self._save_local(task)

    def get(self, task_id: str) -> Optional[Task]:
        return self._load_local(task_id)

    def get_all_tasks(self, limit: int = 100) -> list:
        tasks = list(self._iter_local_tasks() or [])
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def delete(self, task_id: str):
        try:
            task_path = self._get_task_path(task_id)
            if task_path.exists():
                task_path.unlink()
            self.cache.delete(task_id)
        except Exception as exc:
            print("[TaskStore] Failed to delete local task {}: {}".format(task_id, exc))

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
        return None

    def release_dedupe(self, task: Task):
        return None

    def get_unfinished_tasks(self) -> list:
        return [
            task
            for task in self.get_all_tasks(limit=10000)
            if task.status in UNFINISHED_STATUSES
        ]

    def _delete_file(self, path) -> int:
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
        protected_paths: Optional[Set[Path]] = None,
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
            if ".queue" in path.parts or path.name == ".gitkeep":
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

            self.delete(task.id)
            cleaned_count += 1
            print("[Cleanup] Deleted task: {}".format(task.id))

        protected_paths: Set[Path] = set()
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
        return cleaned_count


# ============ Local File Queue ============

class LocalFileQueue:
    def __init__(self, download_dir=None):
        self.data_dir = _normalize_download_dir(download_dir)
        self.queue_dir = self.data_dir / ".queue"
        self.pending_dir = self.queue_dir / "pending"
        self.running_dir = self.queue_dir / "running"
        self.failed_dir = self.queue_dir / "failed"
        self.heartbeat_dir = self.queue_dir / "heartbeat"
        self.lock_path = self.queue_dir / "submit.lock"
        for path in [
            self.pending_dir,
            self.running_dir,
            self.failed_dir,
            self.heartbeat_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def submit_lock(self) -> FileLock:
        return FileLock(self.lock_path)

    def _job_name(self, task: Task) -> str:
        return "{}_{}.json".format(int(task.created_at * 1000), task.id)

    def _payload_for_task(self, task: Task, attempts: int = 0) -> dict:
        return {
            "task_id": task.id,
            "url": task.url,
            "skip_seconds": task.skip_seconds,
            "trim_end_seconds": task.trim_end_seconds,
            "repeat_count": task.repeat_count,
            "attempts": attempts,
            "created_at": task.created_at,
            "updated_at": time.time(),
        }

    def enqueue(self, task: Task, attempts: int = 0):
        _atomic_write_json(
            self.pending_dir / self._job_name(task),
            self._payload_for_task(task, attempts=attempts),
        )

    def _read_payload(self, path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print("[LocalQueue] Failed to read queue file {}: {}".format(path, exc))
            return None

    def _job_exists(self, task_id: str) -> bool:
        for directory in [self.pending_dir, self.running_dir]:
            for path in directory.glob("*_{}.json".format(task_id)):
                if path.exists():
                    return True
        return False

    def claim_next(self, worker_id: str) -> Optional[Tuple[Path, dict]]:
        for pending_path in sorted(self.pending_dir.glob("*.json")):
            running_path = self.running_dir / pending_path.name
            try:
                os.replace(str(pending_path), str(running_path))
            except FileNotFoundError:
                continue
            except OSError as exc:
                print("[LocalQueue] Failed to claim task {}: {}".format(pending_path, exc))
                continue

            payload = self._read_payload(running_path)
            if not payload:
                if running_path.exists():
                    running_path.unlink()
                continue
            payload["worker_id"] = worker_id
            payload["claimed_at"] = time.time()
            payload["updated_at"] = time.time()
            _atomic_write_json(running_path, payload)
            return running_path, payload
        return None

    def complete(self, running_path: Path):
        if running_path.exists():
            running_path.unlink()

    def requeue(self, running_path: Path, payload: dict, error: str):
        payload["updated_at"] = time.time()
        payload["last_error"] = error
        target = self.pending_dir / running_path.name
        _atomic_write_json(target, payload)
        if running_path.exists():
            running_path.unlink()

    def fail_final(self, running_path: Path, payload: dict, error: str):
        payload["updated_at"] = time.time()
        payload["last_error"] = error
        target = self.failed_dir / running_path.name
        _atomic_write_json(target, payload)
        if running_path.exists():
            running_path.unlink()

    def heartbeat(self, worker_id: str):
        _atomic_write_json(
            self.heartbeat_dir / "{}.json".format(worker_id),
            {
                "worker_id": worker_id,
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "updated_at": time.time(),
            },
        )

    def visible_workers(self) -> List[str]:
        now = time.time()
        heartbeat_seconds = float(
            os.environ.get("TANGDOU_LOCAL_WORKER_HEARTBEAT_SECONDS", 10)
        )
        max_age = max(heartbeat_seconds * 3, 30)
        workers = []
        for path in self.heartbeat_dir.glob("*.json"):
            payload = self._read_payload(path)
            if not payload:
                continue
            updated_at = float(payload.get("updated_at") or 0)
            if now - updated_at <= max_age:
                workers.append(str(payload.get("worker_id") or path.stem))
        return sorted(workers)

    def recover_stale_running(self, store: TaskStore) -> int:
        timeout = float(
            os.environ.get("TANGDOU_LOCAL_QUEUE_JOB_TIMEOUT_SECONDS", 1800)
        )
        now = time.time()
        restored = 0
        for running_path in sorted(self.running_dir.glob("*.json")):
            payload = self._read_payload(running_path)
            if not payload:
                if running_path.exists():
                    running_path.unlink()
                continue
            claimed_at = float(payload.get("claimed_at") or running_path.stat().st_mtime)
            if now - claimed_at < timeout:
                continue

            task = store.get(str(payload.get("task_id", "")))
            if task and task.status in UNFINISHED_STATUSES:
                task.status = "queued"
                task.message = "Worker timeout, task requeued"
                task.add_log("warning", "Worker timeout, task requeued")
                store.save(task)

            self.requeue(running_path, payload, "worker timeout")
            restored += 1
        return restored

    def requeue_unfinished(self, store: TaskStore) -> int:
        restored = 0
        for task in store.get_unfinished_tasks():
            if self._job_exists(task.id):
                continue
            task.status = "queued"
            task.message = "Task recovered on worker start"
            task.add_log("info", "Requeued on worker start")
            store.save(task)
            self.enqueue(task)
            restored += 1
            print("[Recovery] Restored task: {}".format(task.id))
        return restored

    def stats(self) -> dict:
        workers = self.visible_workers()
        return {
            "backend": "local",
            "queued": len(list(self.pending_dir.glob("*.json"))),
            "started": len(list(self.running_dir.glob("*.json"))),
            "failed": len(list(self.failed_dir.glob("*.json"))),
            "redis_available": False,
            "worker_count": len(workers),
            "worker_names": workers,
            "workers_visible": len(workers) > 0,
            "queue_dir": str(self.queue_dir),
        }


# ============ Task Processing ============

def _get_status_message(stage: str) -> str:
    messages = {
        "info": "Fetching video info...",
        "downloading": "Downloading video...",
        "download": "Downloading video...",
        "convert": "Converting to MP3...",
        "complete": "Processing complete",
        "completed": "Processing complete",
    }
    return messages.get(stage, stage)


def process_download_task(
    task_id: str,
    url: str,
    skip_seconds: int,
    trim_end_seconds: int = 3,
    repeat_count: int = 2,
):
    print("[LocalWorker] Processing task: {}".format(task_id))
    store = TaskStore()
    downloader = VideoDownloader(str(store.data_dir))

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
                task.add_log("info", "{}: {}%".format(stage, percent))
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

        print("[LocalWorker] Task complete: {}".format(task_id))
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

        print("[LocalWorker] Task failed: {}, error: {}".format(task_id, exc))
        raise


# ============ Local Queue Worker ============

class LocalQueueWorker:
    def __init__(self, download_dir=None):
        self.store = TaskStore(download_dir=download_dir)
        self.queue = LocalFileQueue(self.store.data_dir)
        self.worker_id = (
            os.environ.get("TANGDOU_LOCAL_WORKER_ID")
            or "tangdou-local-{}-{}".format(socket.gethostname(), os.getpid())
        )
        self.poll_seconds = float(
            os.environ.get("TANGDOU_LOCAL_QUEUE_POLL_SECONDS", 2)
        )
        self.max_retries = int(os.environ.get("TANGDOU_LOCAL_QUEUE_RETRIES", 2))
        self._last_recovery = 0.0

    def recover(self) -> int:
        restored = self.queue.recover_stale_running(self.store)
        restored += self.queue.requeue_unfinished(self.store)
        print("[Recovery] Recovery complete, requeued {} tasks".format(restored))
        return restored

    def process_once(self) -> bool:
        self.queue.heartbeat(self.worker_id)
        if time.time() - self._last_recovery > 60:
            self.queue.recover_stale_running(self.store)
            self._last_recovery = time.time()

        claimed = self.queue.claim_next(self.worker_id)
        if not claimed:
            return False

        running_path, payload = claimed
        task_id = str(payload["task_id"])
        try:
            process_download_task(
                task_id,
                str(payload["url"]),
                int(payload.get("skip_seconds", 5)),
                int(payload.get("trim_end_seconds", 3)),
                int(payload.get("repeat_count", 2)),
            )
            self.queue.complete(running_path)
            return True
        except Exception as exc:
            attempts = int(payload.get("attempts", 0)) + 1
            payload["attempts"] = attempts
            if attempts <= self.max_retries:
                task = self.store.get(task_id)
                if task:
                    task.status = "queued"
                    task.message = "Failed, waiting for attempt {}".format(attempts + 1)
                    task.add_log("warning", "Task requeued after failure: {}".format(exc))
                    self.store.save(task)
                self.queue.requeue(running_path, payload, str(exc))
                print("[LocalWorker] Task requeued: {}, attempts={}".format(task_id, attempts))
            else:
                self.queue.fail_final(running_path, payload, str(exc))
                print("[LocalWorker] Task max retries reached: {}".format(task_id))
            return True

    def run_forever(self):
        self.recover()
        while True:
            processed = self.process_once()
            if not processed:
                time.sleep(self.poll_seconds)


# ============ Web-side Task Processor ============

class TaskProcessor:
    """Web-side task manager using the local file queue."""

    def __init__(self, download_dir=None):
        self.download_dir = str(_normalize_download_dir(download_dir))
        self.store = TaskStore(download_dir=self.download_dir)
        self.queue = LocalFileQueue(self.download_dir)
        self._downloader = None
        print("[TaskProcessor] Local directory queue: {}".format(self.queue.queue_dir))

    @property
    def downloader(self):
        if self._downloader is None:
            self._downloader = VideoDownloader(self.download_dir)
        return self._downloader

    def redis_available(self) -> bool:
        return False

    def submit(
        self,
        url: str,
        skip_seconds: int = 5,
        trim_end_seconds: int = 3,
        repeat_count: int = 2,
    ) -> str:
        max_age_hours = get_retention_hours()
        dedupe_key, _vid = build_dedupe_key(
            url,
            skip_seconds,
            trim_end_seconds,
            repeat_count,
        )

        with self.queue.submit_lock():
            duplicate = self.store.find_duplicate(dedupe_key, max_age_hours=max_age_hours)
            if duplicate:
                raise DuplicateTaskError(duplicate.id, duplicate.status)

            task_id = str(uuid.uuid4())[:8]
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
            task.add_log("info", "Task created, added to local queue")
            self.store.save(task)
            self.queue.enqueue(task)

        print("[Task] Submitted: {}, local queue".format(task_id))
        return task_id

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
        stats = self.queue.stats()
        tasks = self.store.get_all_tasks(limit=10000)
        finished = len([task for task in tasks if task.status == "completed"])
        failed = len([task for task in tasks if task.status == "failed"])
        stats["finished"] = finished
        stats["failed"] = max(stats["failed"], failed)
        return stats


def recover_unfinished_tasks(queue=None, redis_conn=None) -> int:
    store = TaskStore()
    local_queue = LocalFileQueue(store.data_dir)
    restored = local_queue.recover_stale_running(store)
    restored += local_queue.requeue_unfinished(store)
    print("[Recovery] Recovery complete, requeued {} tasks".format(restored))
    return restored


_processor = None


def get_processor() -> TaskProcessor:
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor


__all__ = [
    "DuplicateTaskError",
    "LocalQueueWorker",
    "RedisUnavailableError",
    "Task",
    "TaskProcessor",
    "TaskStore",
    "build_dedupe_key",
    "get_processor",
    "get_retention_hours",
    "process_download_task",
    "recover_unfinished_tasks",
]
