"""
任务处理器 - 后台队列处理
使用文件存储支持多进程共享
"""

import os
import threading
import queue
import time
import uuid
import json
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path

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
    logs: list = field(default_factory=list)  # 新增：执行日志
    
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
        """添加日志"""
        self.logs.append({
            'time': time.strftime('%H:%M:%S'),
            'level': level,
            'message': message
        })


class TaskStore:
    """任务存储 - 使用文件支持多进程共享"""
    
    def __init__(self, data_dir: str = "static/downloads"):
        # 获取绝对路径 - 从项目根目录计算
        if not os.path.isabs(data_dir):
            # 使用工作目录作为基准，确保多进程一致性
            base_dir = os.getcwd()
            # 如果当前目录不是项目根目录，尝试找到项目根目录
            if not os.path.exists(os.path.join(base_dir, 'app.py')):
                # 尝试从 __file__ 定位
                file_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if os.path.exists(os.path.join(file_dir, 'app.py')):
                    base_dir = file_dir
            data_dir = os.path.join(base_dir, data_dir)
        
        self.data_dir = data_dir
        self.tasks_dir = os.path.join(data_dir, '.tasks')
        os.makedirs(self.tasks_dir, exist_ok=True)
        print(f"[TaskStore] 任务存储目录: {self.tasks_dir}")
    
    def _get_task_file(self, task_id: str) -> str:
        return os.path.join(self.tasks_dir, f"{task_id}.json")
    
    def save(self, task: Task):
        """保存任务到文件"""
        filepath = self._get_task_file(task.id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
    
    def get(self, task_id: str) -> Optional[Task]:
        """从文件读取任务"""
        filepath = self._get_task_file(task_id)
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            task = Task(
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
            return task
        except Exception as e:
            print(f"[TaskStore] 读取任务失败: {e}")
            return None
    
    def cleanup_old(self, max_age_hours: int = 24):
        """清理旧任务文件"""
        now = time.time()
        for filename in os.listdir(self.tasks_dir):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(self.tasks_dir, filename)
            if os.path.getmtime(filepath) < now - max_age_hours * 3600:
                try:
                    os.remove(filepath)
                except:
                    pass


class TaskProcessor:
    """任务处理器 - 后台队列处理"""
    
    def __init__(self, download_dir: str = "static/downloads", max_workers: int = 2):
        self.download_dir = download_dir
        self.downloader = VideoDownloader(download_dir)
        self.task_queue = queue.Queue()
        self.store = TaskStore(download_dir)  # 使用文件存储
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
                if task is None:
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
            task.add_log('info', '开始下载视频')
            self._update_task(task)
            
            def progress_callback(stage, percent):
                task.status = stage
                task.progress = percent
                task.message = self._get_status_message(stage)
                task.add_log('info', f'{stage}: {percent}%')
                self._update_task(task)
            
            def task_check():
                return True
            
            # 执行处理流程
            result = self.downloader.process_pipeline(
                task.url,
                skip_seconds=task.skip_seconds,
                progress_callback=progress_callback,
                task_check=task_check
            )
            
            # 清理视频文件
            if "video_path" in result:
                self.downloader.cleanup(result["video_path"], keep_video=False)
            
            task.result = result
            task.status = "completed"
            task.progress = 100
            task.message = "处理完成"
            task.completed_at = time.time()
            task.add_log('success', '处理完成')
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.message = f"处理失败: {e}"
            task.completed_at = time.time()
            task.add_log('error', str(e))
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
        """更新任务状态（保存到文件）"""
        self.store.save(task)
    
    def submit(self, url: str, skip_seconds: int = 5) -> str:
        """提交新任务"""
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            url=url,
            skip_seconds=skip_seconds
        )
        task.add_log('info', '任务已创建')
        
        # 先保存到文件
        self.store.save(task)
        
        # 加入处理队列
        self.task_queue.put(task)
        print(f"[任务] 提交新任务: {task_id}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态（从文件读取）"""
        return self.store.get(task_id)
    
    def _cleanup_loop(self):
        """定期清理旧文件"""
        while not self._shutdown:
            time.sleep(3600)
            try:
                self.store.cleanup_old(max_age_hours=24)
            except Exception as e:
                print(f"[清理] 错误: {e}")
    
    def shutdown(self):
        """关闭处理器"""
        self._shutdown = True
        for _ in self._workers:
            self.task_queue.put(None)
        for w in self._workers:
            w.join(timeout=5)
        print("[任务处理器] 已关闭")


# 全局处理器实例（每个进程有自己的实例，但通过文件共享数据）
_processor = None

def get_processor() -> TaskProcessor:
    """获取全局处理器实例"""
    global _processor
    if _processor is None:
        _processor = TaskProcessor()
    return _processor
