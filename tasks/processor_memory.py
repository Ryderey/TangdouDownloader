"""
内存模式任务处理器 - 用于本地开发（无Redis）
注意：此模式不支持多进程，仅用于开发测试
"""
from __future__ import annotations

import os
import time
import uuid
import json
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional

from modules.downloader import VideoDownloader


@dataclass
class Task:
    """任务对象"""
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
    
    def add_log(self, level: str, message: str):
        self.logs.append({
            'time': time.strftime('%H:%M:%S'),
            'level': level,
            'message': message
        })


class TaskStore:
    """内存任务存储"""
    
    _tasks = {}  # 类级别存储
    
    def __init__(self):
        pass
    
    def save(self, task: Task):
        """保存任务"""
        TaskStore._tasks[task.id] = task
    
    def get(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return TaskStore._tasks.get(task_id)
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取所有任务"""
        tasks = sorted(TaskStore._tasks.values(), 
                      key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]
    
    def cleanup_old(self, max_age_hours: int = 24, delete_mp3: bool = True) -> int:
        """清理旧任务"""
        now = time.time()
        cutoff = now - max_age_hours * 3600
        to_delete = []
        
        for task_id, task in TaskStore._tasks.items():
            if task.completed_at and task.completed_at < cutoff:
                to_delete.append(task_id)
                # 删除MP3文件
                if delete_mp3 and task.result:
                    mp3_path = task.result.get('mp3_path')
                    if mp3_path and os.path.exists(mp3_path):
                        try:
                            os.remove(mp3_path)
                        except:
                            pass
        
        for task_id in to_delete:
            del TaskStore._tasks[task_id]
        
        return len(to_delete)


class TaskProcessor:
    """内存模式任务处理器 - 仅用于开发"""
    
    def __init__(self, download_dir: str = "static/downloads"):
        self.download_dir = download_dir
        self.downloader = VideoDownloader(download_dir)
        self.store = TaskStore()
        self.task_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        print("[TaskProcessor] Memory mode (dev only)")
    
    def _worker(self):
        """工作线程"""
        while True:
            try:
                task = self.task_queue.get(timeout=1)
                if task is None:
                    break
                self._process_task(task)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print("[Worker] Error: {}".format(e))
    
    def _process_task(self, task: Task):
        """处理任务"""
        video_path = None
        try:
            task.status = "downloading"
            task.message = "Downloading video..."
            task.add_log('info', 'Start downloading video')
            self.store.save(task)
            
            def progress_callback(stage, percent):
                task.status = stage
                task.progress = percent
                task.message = {
                    "info": "获取视频信息...",
                    "download": "正在下载视频...",
                    "convert": "正在转换为MP3...",
                    "complete": "处理完成"
                }.get(stage, stage)
                task.add_log('info', f'{stage}: {percent}%')
                self.store.save(task)
            
            result = self.downloader.process_pipeline(
                task.url,
                skip_seconds=task.skip_seconds,
                progress_callback=progress_callback
            )
            
            video_path = result.get("video_path")
            if video_path:
                self.downloader.cleanup(video_path, keep_video=False)
            
            task.result = result
            task.status = "completed"
            task.progress = 100
            task.message = "Processing complete"
            task.completed_at = time.time()
            task.add_log('success', 'Processing complete')
            
        except Exception as e:
            if video_path:
                try:
                    self.downloader.cleanup(video_path, keep_video=False)
                except:
                    pass
            
            task.status = "failed"
            task.error = str(e)
            task.message = "Processing failed: {}".format(e)
            task.completed_at = time.time()
            task.add_log('error', str(e))
        
        self.store.save(task)
    
    def submit(self, url: str, skip_seconds: int = 5) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds,
            status="queued",
            message="Waiting..."
        )
        task.add_log('info', 'Task created')
        self.store.save(task)
        self.task_queue.put(task)
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.store.get(task_id)
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取所有任务"""
        return self.store.get_all_tasks(limit)
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """清理旧文件"""
        return self.store.cleanup_old(max_age_hours, delete_mp3=True)
    
    def get_queue_stats(self) -> dict:
        """队列统计"""
        return {
            'queued': self.task_queue.qsize(),
            'started': 0,
            'finished': 0,
            'failed': 0,
        }


# 全局处理器
_processor = None

def get_processor():
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor
