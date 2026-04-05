"""
任务处理器 - 使用Redis Queue (RQ) 实现
支持多进程安全的任务队列
"""

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
    print("[警告] Redis/RQ未安装，使用降级模式（仅适用于开发）")

from modules.downloader import VideoDownloader


# Redis连接配置
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)


def get_redis_connection():
    """获取Redis连接 - 用于任务状态存储（启用decode_responses）"""
    if not REDIS_AVAILABLE:
        raise RuntimeError("Redis模块未安装")
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
        raise RuntimeError("Redis模块未安装")
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
            print(f"[TaskStore] 解析任务失败: {e}")
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
                            print(f"[Cleanup] 已删除MP3: {mp3_path}")
                        except Exception as e:
                            print(f"[Cleanup] 删除MP3失败: {e}")
                    elif mp3_filename:
                        # 尝试从常见路径删除
                        for base_dir in ['static/downloads', '/home/ryl/script/tangdou-web/static/downloads']:
                            full_path = os.path.join(base_dir, mp3_filename)
                            if os.path.exists(full_path):
                                try:
                                    os.remove(full_path)
                                    cleaned_count += 1
                                    print(f"[Cleanup] 已删除MP3: {full_path}")
                                    break
                                except Exception as e:
                                    print(f"[Cleanup] 删除MP3失败: {e}")
                
                # 删除任务记录
                self.delete(task.id)
                cleaned_count += 1
                print(f"[Cleanup] 已删除任务: {task.id}")
        
        return cleaned_count


# ============ RQ 任务函数 ============

def process_download_task(task_id: str, url: str, skip_seconds: int):
    """
    RQ工作进程执行的实际任务
    这个函数在Worker进程中运行
    """
    print(f"[Worker] 开始处理任务: {task_id}")
    
    # 创建独立的存储连接（Worker进程中）
    store = TaskStore()
    downloader = VideoDownloader()
    
    # 获取或创建任务
    task = store.get(task_id)
    if not task:
        task = Task(Task(id=task_id, url=url, skip_seconds=skip_seconds)
    
    video_path = None
    
    try:
        # 更新状态为处理中
        task.status = "downloading"
        task.message = "正在下载视频..."
        task.add_log('info', '开始下载视频')
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
        task.message = "处理完成"
        task.completed_at = time.time()
        task.add_log('success', '处理完成')
        store.save(task)
        
        print(f"[Worker] 任务完成: {task_id}")
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
        task.message = f"处理失败: {e}"
        task.completed_at = time.time()
        task.add_log('error', str(e))
        store.save(task)
        
        print(f"[Worker] 任务失败: {task_id}, 错误: {e}")
        raise


def _get_status_message(stage: str) -> str:
    """获取状态描述"""
    messages = {
        "info": "获取视频信息...",
        "download": "正在下载视频...",
        "convert": "正在转换为MP3...",
        "complete": "处理完成"
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
                "Redis/RQ模块未安装。请在生产环境安装: pip install redis rq\n"
                "或使用内存模式: from tasks.processor_memory import get_processor"
            )
        
        # 连接到Redis用于任务状态存储
        self.redis_conn = get_redis_connection()
        self.store = TaskStore(self.redis_conn)
        # 连接到Redis用于RQ队列（使用不同的连接配置）
        self.rq_redis_conn = get_rq_redis_connection()
        self.queue = Queue('tangdou', connection=self.rq_redis_conn)
        
        print(f"[TaskProcessor] 已连接到Redis: {REDIS_HOST}:{REDIS_PORT}")
        print(f"[TaskProcessor] 队列: tangdou")
    
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
            message="等待处理..."
        )
        task.add_log('info', '任务已创建，加入队列')
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
        
        print(f"[任务] 提交成功: {task_id}, RQ job: {job.id}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self.store.get(task_id)
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取最近的任务列表"""
        return self.store.get_all_tasks(limit)
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """手动触发清理"""
        print(f"[清理] 开始清理，保留时间: {max_age_hours} 小时")
        count = self.store.cleanup_old(max_age_hours=max_age_hours, delete_mp3=True)
        print(f"[清理] 完成，共清理 {count} 个文件")
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