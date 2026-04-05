"""
视频下载器 - 使用FFmpeg进行高效处理
优化策略：下载低清视频 + 剪前5秒广告 + 转MP3
"""

import os
import re
import subprocess
import requests
import time
from typing import Callable, Optional, Tuple

from .tangdou import VideoAPI
from .headers import headers


class VideoDownloader:
    """视频下载器 - 专为音频提取优化"""
    
    # 清晰度优先级（从低到高）
    QUALITY_ORDER = ['V360P', 'H360P', 'V540P', 'H540P', 'V720P', 'H720P', 'V1080P', 'H1080P', 'unknown']
    
    def __init__(self, download_dir: str = "static/downloads"):
        # 转换为绝对路径
        if not os.path.isabs(download_dir):
            base_dir = self._get_base_dir()
            download_dir = os.path.join(base_dir, download_dir)
        
        self.download_dir = download_dir
        self.api = VideoAPI()
        os.makedirs(download_dir, exist_ok=True)
        print(f"[VideoDownloader] 下载目录: {self.download_dir}")
        
        # 检查FFmpeg是否可用
        self._check_ffmpeg()
    
    def _get_base_dir(self) -> str:
        """获取项目根目录"""
        # 方法1: 从环境变量获取
        env_dir = os.environ.get('TANGDOU_BASE_DIR')
        if env_dir and os.path.exists(os.path.join(env_dir, 'app.py')):
            return env_dir
        
        # 方法2: 从当前文件位置推导（modules/downloader.py -> 项目根目录）
        file_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.exists(os.path.join(file_dir, 'app.py')):
            return file_dir
        
        # 方法3: 从工作目录获取
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, 'app.py')):
            return cwd
        
        # 方法4: 尝试常见路径
        for path in ['/home/ryl/script/tangdou-web', '/home/ryl/tangdou-mp3']:
            if os.path.exists(os.path.join(path, 'app.py')):
                return path
        
        # 兜底：使用当前文件所在目录的上级
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def _check_ffmpeg(self):
        """检查FFmpeg是否已安装"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg 未安装，请先安装 FFmpeg")
    
    def get_info(self, url_or_vid: str) -> dict:
        """获取视频信息"""
        return self.api.get_video_info(url_or_vid)
    
    def select_lowest_quality(self, urls: dict) -> Tuple[str, str]:
        """
        选择最低清晰度（节省下载流量，因为只需要音频）
        :return: (清晰度名称, URL)
        """
        for quality in self.QUALITY_ORDER:
            if quality in urls:
                return quality, urls[quality]
        
        # 如果没有匹配的，返回第一个
        first_key = list(urls.keys())[0]
        return first_key, urls[first_key]
    
    def download(
        self, 
        video_info: dict, 
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        下载视频（选择最低清晰度）
        :return: 下载后的文件路径
        """
        name = video_info["name"]
        urls = video_info["urls"]
        
        # 选择最低清晰度
        quality, url = self.select_lowest_quality(urls)
        
        # 清理文件名中的非法字符
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", name)
        filename = f"{safe_name}_{quality}.mp4"
        filepath = os.path.join(self.download_dir, filename)
        
        # 如果文件已存在，直接返回
        if os.path.exists(filepath):
            print(f"[下载] 文件已存在: {filename}")
            return filepath
        
        print(f"[下载] 选择清晰度: {quality}")
        print(f"[下载] 开始下载: {filename}")
        
        # 下载
        header = headers(url).buildHeader()
        response = requests.get(url, headers=header, stream=True)
        total_size = int(response.headers.get("content-length", 0))
        
        downloaded = 0
        chunk_size = 8192
        
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)
        
        print(f"[下载] 完成: {filename} ({downloaded/1024/1024:.2f} MB)")
        return filepath
    
    def clip_and_convert(
        self, 
        input_path: str, 
        output_name: str,
        clip_start: int = 5,  # 默认剪掉前5秒
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        使用FFmpeg剪辑并转换为MP3
        :param input_path: 输入视频路径
        :param output_name: 输出文件名（不含扩展名）
        :param clip_start: 开始时间（秒），默认5秒跳过广告
        :return: MP3文件路径
        """
        output_path = os.path.join(self.download_dir, f"{output_name}.mp3")
        
        # 如果文件已存在，直接返回
        if os.path.exists(output_path):
            print(f"[转换] 文件已存在: {output_name}.mp3")
            return output_path
        
        # 构建FFmpeg命令
        # -ss 5: 从第5秒开始（跳过广告）
        # -vn: 禁用视频
        # -ar 44100: 音频采样率
        # -ac 2: 双声道
        # -b:a 192k: 比特率
        cmd = [
            'ffmpeg',
            '-y',  # 覆盖输出文件
            '-ss', str(clip_start),  # 从第N秒开始
            '-i', input_path,  # 输入文件
            '-vn',  # 不要视频
            '-ar', '44100',  # 采样率
            '-ac', '2',  # 声道数
            '-b:a', '192k',  # 音频比特率
            '-f', 'mp3',  # 输出格式
            output_path
        ]
        
        print(f"[转换] FFmpeg剪辑并转MP3: {output_name}.mp3")
        print(f"[转换] 跳过前 {clip_start} 秒")
        
        # 执行FFmpeg
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            
            if progress_callback:
                progress_callback(100)
            
            print(f"[转换] 完成: {output_name}.mp3")
            return output_path
            
        except subprocess.CalledProcessError as e:
            print(f"[转换] FFmpeg错误: {e.stderr}")
            raise RuntimeError(f"FFmpeg转换失败: {e.stderr}")
    
    def process_pipeline(
        self,
        url_or_vid: str,
        skip_seconds: int = 5,  # 默认跳过前5秒广告
        progress_callback: Optional[Callable[[str, int], None]] = None,
        task_check: Optional[Callable[[], bool]] = None
    ) -> dict:
        """
        完整处理流程：下载(低清) -> 剪辑(去广告) -> 转MP3
        :return: {
            "video_path": "原始视频路径",
            "mp3_path": "MP3路径",
            "mp3_filename": "MP3文件名"
        }
        """
        result = {}
        
        # 1. 获取信息
        if progress_callback:
            progress_callback("info", 10)
        info = self.get_info(url_or_vid)
        
        if task_check and not task_check():
            raise RuntimeError("任务已取消")
        
        # 2. 下载（选择最低清晰度）
        if progress_callback:
            progress_callback("download", 30)
        
        def download_progress(downloaded, total):
            if total > 0 and progress_callback:
                percent = int(30 + (downloaded / total) * 30)  # 30-60%
                progress_callback("download", percent)
        
        video_path = self.download(info, download_progress)
        result["video_path"] = video_path
        
        if task_check and not task_check():
            raise RuntimeError("任务已取消")
        
        # 3. 剪辑并转MP3
        if progress_callback:
            progress_callback("convert", 70)
        
        # 生成输出文件名
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", info["name"])
        mp3_path = self.clip_and_convert(
            video_path, 
            safe_name,
            clip_start=skip_seconds
        )
        
        result["mp3_path"] = mp3_path
        result["mp3_filename"] = os.path.basename(mp3_path)
        result["title"] = info["name"]
        
        if progress_callback:
            progress_callback("complete", 100)
        
        return result
    
    def cleanup(self, video_path: str, keep_video: bool = False):
        """
        清理临时文件
        :param video_path: 视频文件路径
        :param keep_video: 是否保留视频文件
        """
        if not keep_video and os.path.exists(video_path):
            try:
                os.remove(video_path)
                print(f"[清理] 已删除临时视频: {os.path.basename(video_path)}")
            except Exception as e:
                print(f"[清理] 删除失败: {e}")
