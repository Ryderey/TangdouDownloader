"""
任务处理器 - 使用Redis Queue (RQ) 实现
支持多进程安全的任务队列
"""
from __future__ import annotations

import os
import time
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

# 尝试导入Redis和RQ，如果失败则使用降级方案
try:
    import redis
    from rq import Queue, Retry
    from rq.job import Job
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("[WARNING] Redis/RQ not installed, using degraded mode (dev only)")

from modules.downloader import VideoDownloader


# Redis连接配置
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)


def get_redis_connection():
    """获取Redis连接 - 用于任务状态存储（启用decode_responses）"""
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
    """获取Redis连接 - 用于RQ队列（禁用decode_responses）"""
    if not REDIS_AVAILABLE:
        raise RuntimeError("Redis module not installed")
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=False,  # RQ需要原始字节数据
        socket_connect_timeout=5,
        socket_timeout=5,
    )


@dataclass
class Task:
    """任务对象 - 用于状态存储"""
    id: str
    url: str
    skip_seconds: int = 5
    status: str = "pending"
    progress: int = 0
    message: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    logs: list = field(default_factory=list)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'url': self.url,
            'skip_seconds': self.skip_seconds,
            'status': self.status,
            'progress': self.progress,
            'message': self.message,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
            'logs': self.logs
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """从字典创建"""
        return cls(
            id=data['id'],
            url=data['url'],
            skip_seconds=data.get('skip_seconds', 5),
            status=data.get('status', 'pending'),
            progress=data.get('progress', 0),
            message=data.get('message', ''),
            result=data.get('result', {}),
            error=data.get('error', ''),
            created_at=data.get('created_at', time.time()),
            completed_at=data.get('completed_at'),
            logs=data.get('logs', [])
        )
    
    def add_log(self, level: str, message: str):
        """添加日志"""
        self.logs.append({
            'time': time.strftime('%H:%M:%S'),
            'level': level,
            'message': message
        })


class TaskStore:
    """任务存储 - 使用Redis作为状态存储"""
    
    # 任务状态在Redis中的前缀
    TASK_KEY_PREFIX = "tangdou:task:"
    TASK_IDS_KEY = "tangdou:task_ids"
    
    def __init__(self, redis_conn=None):
        self.redis = redis_conn or get_redis_connection()
    
    def _get_task_key(self, task_id: str) -> str:
        return f"{self.TASK_KEY_PREFIX}{task_id}"
    
    def save(self, task: Task):
        """保存任务到Redis"""
        key = self._get_task_key(task.id)
        data = json.dumps(task.to_dict(), ensure_ascii=False)
        self.redis.setex(key, 86400 * 7, data)  # 保留7天
        # 同时加入任务ID列表
        self.redis.sadd(self.TASK_IDS_KEY, task.id)
        self.redis.expire(self.TASK_IDS_KEY, 86400 * 7)
    
    def get(self, task_id: str) -> Optional[Task]:
        """从Redis读取任务"""
        key = self._get_task_key(task_id)
        data = self.redis.get(key)
        if not data:
            return None
        try:
            task_data = json.loads(data)
            return Task.from_dict(task_data)
        except Exception as e:
            print("[TaskStore] Failed to parse task: {}".format(e))
            return None
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取所有任务"""
        task_ids = self.redis.smembers(self.TASK_IDS_KEY)
        tasks = []
        for task_id in task_ids:
            task = self.get(task_id)
            if task:
                tasks.append(task)
        # 按创建时间倒序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]
    
    def delete(self, task_id: str):
        """删除任务"""
        key = self._get_task_key(task_id)
        self.redis.delete(key)
        self.redis.srem(self.TASK_IDS_KEY, task_id)
    
    def cleanup_old(self, max_age_hours: int = 24, delete_mp3: bool = True) -> int:
        """
        清理旧任务及关联的MP3文件
        :return: 清理的文件数量
        """
        from pathlib import Path
        
        now = time.time()
        cutoff_time = now - max_age_hours * 3600
        cleaned_count = 0
        
        # 获取所有任务
        all_tasks = self.get_all_tasks(limit=1000)
        
        for task in all_tasks:
            # 检查是否过期（已完成/失败的任务）
            if task.completed_at and task.completed_at < cutoff_time:
                # 删除关联的MP3文件
                if delete_mp3 and task.result:
                    mp3_path = task.result.get('mp3_path')
                    mp3_filename = task.result.get('mp3_filename')
                    
                    if mp3_path and os.path.exists(mp3_path):
                        try:
                            os.remove(mp3_path)
                            cleaned_count += 1
                            print("[Cleanup] Deleted MP3: {}".format(mp3_path))
                        except Exception as e:
                            print("[Cleanup] Failed to delete MP3: {}".format(e))
                    elif mp3_filename:
                        # 尝试从项目下载目录删除
                        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        for base_dir in ['static/downloads', os.path.join(_base, 'static/downloads')]:
                            full_path = os.path.join(base_dir, mp3_filename)
                            if os.path.exists(full_path):
                                try:
                                    os.remove(full_path)
                                    cleaned_count += 1
                                    print("[Cleanup] Deleted MP3: {}".format(full_path))
                                    break
                                except Exception as e:
                                    print("[Cleanup] Failed to delete MP3: {}".format(e))
                
                # 删除任务记录
                self.delete(task.id)
                cleaned_count += 1
                print("[Cleanup] Deleted task: {}".format(task.id))
        
        return cleaned_count


# ============ RQ 任务函数 ============

def process_download_task(task_id: str, url: str, skip_seconds: int):
    """
    RQ工作进程执行的实际任务
    这个函数在Worker进程中运行
    """
    print("[Worker] Processing task: {}".format(task_id))
    
    # 创建独立的存储连接（Worker进程中）
    store = TaskStore()
    downloader = VideoDownloader()
    
    # 获取或创建任务
    task = store.get(task_id)
    if not task:
        task = Task(id=task_id, url=url, skip_seconds=skip_seconds)
    
    video_path = None
    
    try:
        # 更新状态为处理中
        task.status = "downloading"
        task.message = "Downloading video..."
        task.add_log('info', 'Start downloading video')
        store.save(task)
        
        # 优化：减少进度更新频率
        last_update_percent = 0
        last_update_stage = ""
        
        def progress_callback(stage, percent):
            nonlocal last_update_percent, last_update_stage
            
            # 只在以下情况更新状态：
            # 1. 阶段发生变化（如从 downloading 到 converting）
            # 2. 进度变化超过 10%
            # 3. 达到完成状态（100%）
            should_update = (
                stage != last_update_stage or 
                abs(percent - last_update_percent) >= 10 or 
                percent == 100
            )
            
            if should_update:
                task.status = stage
                task.progress = percent
                task.message = _get_status_message(stage)
                task.add_log('info', f'{stage}: {percent}%')
                store.save(task)
                last_update_percent = percent
                last_update_stage = stage
        
        # 执行处理流程
        result = downloader.process_pipeline(
            url,
            skip_seconds=skip_seconds,
            progress_callback=progress_callback
        )
        
        # 清理视频文件
        video_path = result.get("video_path")
        if video_path:
            downloader.cleanup(video_path, keep_video=False)
        
        # 更新完成状态
        task.result = result
        task.status = "completed"
        task.progress = 100
        task.message = "Processing complete"
        task.completed_at = time.time()
        task.add_log('success', 'Processing complete')
        store.save(task)
        
        print("[Worker] Task complete: {}".format(task_id))
        return result
        
    except Exception as e:
        # 异常时清理临时文件
        if video_path:
            try:
                downloader.cleanup(video_path, keep_video=False)
            except:
                pass
        
        # 更新失败状态
        task.status = "failed"
        task.error = str(e)
        task.message = "Processing failed: {}".format(e)
        task.completed_at = time.time()
        task.add_log('error', str(e))
        store.save(task)
        
        print("[Worker] Task failed: {}, error: {}".format(task_id, e))
        raise


def _get_status_message(stage: str) -> str:
    """获取状态描述"""
    messages = {
        "info": "Fetching video info...",
        "download": "Downloading video...",
        "convert": "Converting to MP3...",
        "complete": "Processing complete"
    }
    return messages.get(stage, stage)


# ============ Web 端任务管理器 ============

class TaskProcessor:
    """
    Web端任务处理器
    负责提交任务到RQ队列，查询状态
    """
    
    def __init__(self, download_dir: str = "static/downloads"):
        self.download_dir = download_dir
        # Web进程不需要VideoDownloader（只有Worker需要）
        self._downloader = None
        
        # 检查Redis是否可用
        if not REDIS_AVAILABLE:
            raise RuntimeError(
                "Redis/RQ module not installed. Install for production: pip install redis rq\n"
                "Or use memory mode: from tasks.processor_memory import get_processor"
            )
        
        # 连接到Redis用于任务状态存储
        self.redis_conn = get_redis_connection()
        self.store = TaskStore(self.redis_conn)
        # 连接到Redis用于RQ队列（使用不同的连接配置）
        self.rq_redis_conn = get_rq_redis_connection()
        self.queue = Queue('tangdou', connection=self.rq_redis_conn)
        
        print("[TaskProcessor] Connected to Redis: {}:{}".format(REDIS_HOST, REDIS_PORT))
        print("[TaskProcessor] Queue: tangdou")
    
    @property
    def downloader(self):
        """懒加载VideoDownloader（仅在需要时初始化）"""
        if self._downloader is None:
            self._downloader = VideoDownloader(self.download_dir)
        return self._downloader
    
    def submit(self, url: str, skip_seconds: int = 5) -> str:
        """提交新任务到队列"""
        task_id = str(uuid.uuid4())[:8]
        
        # 先创建任务记录
        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds,
            status="queued",
            message="Waiting..."
        )
        task.add_log('info', 'Task created, added to queue')
        self.store.save(task)
        
        # 提交到RQ队列
        job = self.queue.enqueue(
            process_download_task,
            task_id,
            url,
            skip_seconds,
            job_id=task_id,
            retry=Retry(max=2),  # 失败重试2次
            job_timeout=600,      # 10分钟超时
        )
        
        print("[Task] Submitted: {}, RQ job: {}".format(task_id, job.id))
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self.store.get(task_id)
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取最近的任务列表"""
        return self.store.get_all_tasks(limit)
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """手动触发清理"""
        print("[Cleanup] Starting cleanup, retention: {} hours".format(max_age_hours))
        count = self.store.cleanup_old(max_age_hours=max_age_hours, delete_mp3=True)
        print("[Cleanup] Complete, {} files cleaned".format(count))
        return count
    
    def get_queue_stats(self) -> dict:
        """获取队列统计信息"""
        return {
            'queued': self.queue.count,
            'started': self.queue.started_job_registry.count,
            'finished': self.queue.finished_job_registry.count,
            'failed': self.queue.failed_job_registry.count,
        }


# 全局处理器实例
_processor = None

def get_processor() -> TaskProcessor:
    """获取全局处理器实例"""
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor


# Win7 分支默认使用本地文件队列（无需 Redis）
# 设置 TANGDOU_QUEUE_BACKEND=redis 可切换回 Redis 模式
_BACKEND = os.environ.get("TANGDOU_QUEUE_BACKEND", "local").strip().lower()
if _BACKEND in {"redis", "rq"}:
    from tasks.reliable_processor import *  # noqa: F401,F403,E402
else:
    from tasks.local_processor import *  # noqa: F401,F403,E402
