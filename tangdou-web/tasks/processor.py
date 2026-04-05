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
    
    def cleanup_old(self, max_age_hours: int = 24, delete_mp3: bool = True) -> int:
        """
        清理旧任务文件及关联的MP3文件
        :param max_age_hours: 文件保留时间（小时）
        :param delete_mp3: 是否同时删除MP3文件
        :return: 清理的文件数量
        """
        now = time.time()
        cutoff_time = now - max_age_hours * 3600
        cleaned_count = 0
        
        for filename in os.listdir(self.tasks_dir):
            if not filename.endswith('.json'):
                continue
                
            filepath = os.path.join(self.tasks_dir, filename)
            
            # 检查文件是否过期
            if os.path.getmtime(filepath) < cutoff_time:
                # 先读取任务信息，获取MP3文件路径
                mp3_files_to_delete = []
                if delete_mp3:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            task_data = json.load(f)
                        
                        # 获取MP3文件路径
                        result = task_data.get('result', {})
                        mp3_path = result.get('mp3_path')
                        mp3_filename = result.get('mp3_filename')
                        
                        if mp3_path and os.path.exists(mp3_path):
                            mp3_files_to_delete.append(mp3_path)
                        elif mp3_filename:
                            # 尝试拼接完整路径
                            full_path = os.path.join(self.data_dir, mp3_filename)
                            if os.path.exists(full_path):
                                mp3_files_to_delete.append(full_path)
                    except Exception as e:
                        print(f"[Cleanup] 读取任务文件失败: {e}")
                
                # 删除任务JSON文件
                try:
                    os.remove(filepath)
                    cleaned_count += 1
                    print(f"[Cleanup] 已删除任务文件: {filename}")
                except Exception as e:
                    print(f"[Cleanup] 删除任务文件失败: {e}")
                    continue
                
                # 删除关联的MP3文件
                for mp3_file in mp3_files_to_delete:
                    try:
                        os.remove(mp3_file)
                        cleaned_count += 1
                        print(f"[Cleanup] 已删除MP3文件: {os.path.basename(mp3_file)}")
                    except Exception as e:
                        print(f"[Cleanup] 删除MP3文件失败: {e}")
        
        return cleaned_count


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
        video_path = None
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
            
            # 记录视频路径用于后续清理
            video_path = result.get("video_path")
            
            # 清理临时视频文件（保留MP3）
            if video_path:
                self.downloader.cleanup(video_path, keep_video=False)
            
            task.result = result
            task.status = "completed"
            task.progress = 100
            task.message = "处理完成"
            task.completed_at = time.time()
            task.add_log('success', '处理完成')
            
        except Exception as e:
            # 异常时也要清理临时视频文件
            if video_path:
                try:
                    self.downloader.cleanup(video_path, keep_video=False)
                    task.add_log('info', '已清理临时文件')
                except Exception as cleanup_err:
                    task.add_log('warning', f'清理临时文件失败: {cleanup_err}')
            
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
    
    def get_all_tasks(self, limit: int = 100) -> list:
        """获取所有任务列表"""
        tasks = []
        try:
            for filename in os.listdir(self.store.tasks_dir):
                if filename.endswith('.json'):
                    task_id = filename[:-5]  # 去掉 .json
                    task = self.get_task(task_id)
                    if task:
                        tasks.append(task)
        except Exception as e:
            print(f"[任务列表] 读取失败: {e}")
        
        # 按创建时间倒序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        清理旧的MP3文件和任务状态文件
        :param max_age_hours: 文件保留时间（小时），0表示清理所有
        :return: 清理的文件数量
        """
        print(f"[清理] 开始清理，保留时间: {max_age_hours} 小时")
        count = self.store.cleanup_old(max_age_hours=max_age_hours, delete_mp3=True)
        print(f"[清理] 完成，共清理 {count} 个文件")
        return count
    
    def _cleanup_loop(self):
        """定期清理旧文件 - 每小时运行一次"""
        print("[清理] 定时清理任务已启动，间隔: 1小时")
        while not self._shutdown:
            time.sleep(3600)  # 每小时检查一次
            try:
                cleaned = self.store.cleanup_old(max_age_hours=24, delete_mp3=True)
                if cleaned > 0:
                    print(f"[清理] 自动清理完成，共清理 {cleaned} 个文件")
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
