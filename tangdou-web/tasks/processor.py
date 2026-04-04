"""
任务处理器 - 后台队列处理
"""

import os
import threading
import queue
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable

from modules.downloader import VideoDownloader


@dataclass
class Task:
    """任务对象"""
    id: str
    url: str
    skip_seconds: int = 5  # 默认跳过前5秒
    status: str = "pending"  # pending, downloading, converting, completed, failed, cancelled
    progress: int = 0
    message: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
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
            'completed_at': self.completed_at
        }


class TaskProcessor:
    """任务处理器 - 后台队列处理"""
    
    def __init__(self, download_dir: str = "static/downloads", max_workers: int = 2):
        self.download_dir = download_dir
        self.downloader = VideoDownloader(download_dir)
        self.task_queue = queue.Queue()
        self.tasks = {}  # task_id -> Task
        self.lock = threading.Lock()
        self.max_workers = max_workers
        self._shutdown = False
        
        # 启动工作线程
        self._workers = []
        for i in range(max_workers):
            t = threading.Thread(target=self._worker, daemon=True, name=f"Worker-{i}")
            t.start()
            self._workers.append(t)
        
        # 启动清理线程
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        
        print(f"[任务处理器] 已启动 {max_workers} 个工作线程")
    
    def _worker(self):
        """工作线程"""
        while not self._shutdown:
            try:
                task = self.task_queue.get(timeout=1)
                if task is None:  # 退出信号
                    break
                self._process_task(task)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Worker] 错误: {e}")
    
    def _process_task(self, task: Task):
        """处理单个任务"""
        try:
            task.status = "downloading"
            task.message = "正在下载视频..."
            self._update_task(task)
            
            def progress_callback(stage, percent):
                task.status = stage
                task.progress = percent
                task.message = self._get_status_message(stage)
                self._update_task(task)
            
            def task_check():
                # 检查任务是否被取消
                with self.lock:
                    t = self.tasks.get(task.id)
                    return t is not None and t.status != "cancelled"
            
            # 执行处理流程
            result = self.downloader.process_pipeline(
                task.url,
                skip_seconds=task.skip_seconds,
                progress_callback=progress_callback,
                task_check=task_check
            )
            
            # 清理视频文件（只保留MP3）
            if "video_path" in result:
                self.downloader.cleanup(result["video_path"], keep_video=False)
            
            task.result = result
            task.status = "completed"
            task.progress = 100
            task.message = "处理完成"
            task.completed_at = time.time()
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.message = f"处理失败: {e}"
            task.completed_at = time.time()
            print(f"[任务] {task.id} 失败: {e}")
        
        self._update_task(task)
    
    def _get_status_message(self, stage: str) -> str:
        """获取状态描述"""
        messages = {
            "info": "获取视频信息...",
            "download": "正在下载视频...",
            "convert": "正在转换为MP3...",
            "complete": "处理完成"
        }
        return messages.get(stage, stage)
    
    def _update_task(self, task: Task):
        """更新任务状态"""
        with self.lock:
            self.tasks[task.id] = task
    
    def submit(self, url: str, skip_seconds: int = 5) -> str:
        """
        提交新任务
        :return: task_id
        """
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds
        )
        
        with self.lock:
            self.tasks[task_id] = task
        
        self.task_queue.put(task)
        print(f"[任务] 提交新任务: {task_id}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        with self.lock:
            return self.tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task.status in ["pending", "downloading"]:
                task.status = "cancelled"
                return True
        return False
    
    def get_all_tasks(self, limit: int = 50):
        """获取所有任务"""
        with self.lock:
            tasks = list(self.tasks.values())
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]
    
    def _cleanup_loop(self):
        """定期清理旧文件"""
        while not self._shutdown:
            time.sleep(3600)  # 每小时检查一次
            try:
                self.cleanup_old_files(max_age_hours=24)
            except Exception as e:
                print(f"[清理] 错误: {e}")
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        清理旧文件
        :param max_age_hours: 文件最大保留时间（小时）
        """
        now = time.time()
        count = 0
        
        for filename in os.listdir(self.download_dir):
            filepath = os.path.join(self.download_dir, filename)
            if os.path.isfile(filepath):
                age = now - os.path.getmtime(filepath)
                if age > max_age_hours * 3600:
                    try:
                        os.remove(filepath)
                        count += 1
                        print(f"[清理] 删除旧文件: {filename}")
                    except Exception as e:
                        print(f"[清理] 删除失败 {filename}: {e}")
        
        if count > 0:
            print(f"[清理] 共删除 {count} 个旧文件")
        
        return count
    
    def shutdown(self):
        """关闭处理器"""
        self._shutdown = True
        for _ in self._workers:
            self.task_queue.put(None)
        for w in self._workers:
            w.join(timeout=5)
        print("[任务处理器] 已关闭")


# 全局处理器实例
_processor = None

def get_processor() -> TaskProcessor:
    """获取全局处理器实例"""
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor
