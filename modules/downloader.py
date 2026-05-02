"""
视频下载器 - 使用FFmpeg进行高效处理
优化策略：下载低清视频 + 剪前后广告 + 可重复拼接 + 转MP3
"""

import os
import re
import json
import subprocess
import requests
import time
from pathlib import Path
from typing import Any
from typing import Callable, Optional, Tuple

from .tangdou import VideoAPI
from .headers import headers


DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DEFAULT_DOWNLOAD_SEGMENT_BYTES = 2 * 1024 * 1024
DEFAULT_DOWNLOAD_RETRIES = 3


class IncompleteDownloadError(RuntimeError):
    pass


def download_segment_bytes() -> int:
    raw = os.environ.get("TANGDOU_DOWNLOAD_SEGMENT_BYTES")
    if raw is None:
        return DEFAULT_DOWNLOAD_SEGMENT_BYTES
    try:
        return max(int(float(raw)), 256 * 1024)
    except ValueError:
        return DEFAULT_DOWNLOAD_SEGMENT_BYTES


def download_retries() -> int:
    raw = os.environ.get("TANGDOU_DOWNLOAD_RETRIES")
    if raw is None:
        return DEFAULT_DOWNLOAD_RETRIES
    try:
        return max(int(float(raw)), 0)
    except ValueError:
        return DEFAULT_DOWNLOAD_RETRIES


def _parse_content_length(response: requests.Response) -> Optional[int]:
    raw = response.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except ValueError:
        return None
    return length if length >= 0 else None


def _parse_content_range_total(response: requests.Response) -> Optional[int]:
    content_range = response.headers.get("Content-Range", "")
    match = re.search(r"/(\d+)\s*$", content_range)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_content_range(response: requests.Response) -> Optional[tuple[int, int, Optional[int]]]:
    content_range = response.headers.get("Content-Range", "")
    match = re.search(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range)
    if not match:
        return None
    try:
        start = int(match.group(1))
        end = int(match.group(2))
        total = None if match.group(3) == "*" else int(match.group(3))
    except ValueError:
        return None
    return start, end, total


def _expected_download_size(response: requests.Response, existing_size: int) -> Optional[int]:
    content_range_total = _parse_content_range_total(response)
    if content_range_total is not None:
        return content_range_total

    content_length = _parse_content_length(response)
    if content_length is None:
        return None
    if response.status_code == 206:
        return existing_size + content_length
    return content_length


def _response_supports_ranges(response: requests.Response) -> bool:
    return "bytes" in response.headers.get("Accept-Ranges", "").lower()


def _close_response(response: requests.Response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _path_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


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
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg/ffprobe 未安装，请先安装 FFmpeg")

    def _download_headers(self, url: str) -> dict:
        header = headers(url).buildHeader()
        header["Accept-Encoding"] = "identity"
        return header

    def _fetch_download_metadata(self, url: str, header: dict) -> tuple[Optional[int], bool]:
        try:
            response = requests.head(
                url,
                headers=header,
                timeout=15,
                allow_redirects=True,
            )
            try:
                if response.status_code < 400:
                    content_length = _parse_content_length(response)
                    if content_length is not None:
                        return content_length, _response_supports_ranges(response)
            finally:
                _close_response(response)
        except requests.RequestException as error:
            print(f"[下载] HEAD探测失败，尝试Range探测: {error}")

        range_header = dict(header)
        range_header["Range"] = "bytes=0-0"
        try:
            response = requests.get(url, headers=range_header, stream=True, timeout=15)
            try:
                if response.status_code == 206:
                    return _parse_content_range_total(response), True
                if response.status_code == 200:
                    return _parse_content_length(response), False
                response.raise_for_status()
            finally:
                _close_response(response)
        except requests.RequestException as error:
            print(f"[下载] Range探测失败: {error}")

        return None, False

    def _download_without_ranges(
        self,
        url: str,
        destination: Path,
        partial_path: Path,
        header: dict,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        last_error = None
        max_attempts = download_retries() + 1

        for attempt in range(1, max_attempts + 1):
            response = None
            try:
                partial_path.unlink(missing_ok=True)
                response = requests.get(url, headers=header, stream=True, timeout=60)
                response.raise_for_status()
                expected_size = _expected_download_size(response, 0)

                with partial_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                        if chunk:
                            handle.write(chunk)
                            if progress_callback and expected_size:
                                progress_callback(_path_size(partial_path), expected_size)

                downloaded_size = _path_size(partial_path)
                if expected_size is not None and downloaded_size < expected_size:
                    raise IncompleteDownloadError(f"{downloaded_size}/{expected_size} bytes")

                os.replace(partial_path, destination)
                return destination
            except (requests.RequestException, OSError, IncompleteDownloadError) as error:
                last_error = error
                print(
                    f"[下载] 整文件下载重试 {attempt}/{max_attempts}, "
                    f"已下载 {_path_size(partial_path)} bytes, 错误: {error}"
                )
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"视频下载中断，已重试 {download_retries()} 次仍未完成"
                    ) from error
                time.sleep(min(2 ** (attempt - 1), 5))
            finally:
                if response is not None:
                    _close_response(response)

        raise RuntimeError(f"视频下载失败: {last_error}")

    def _append_download_range(
        self,
        url: str,
        partial_path: Path,
        start: int,
        end: int,
        total_size: int,
        header: dict,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        range_header = dict(header)
        range_header["Range"] = f"bytes={start}-{end}"
        response = requests.get(url, headers=range_header, stream=True, timeout=60)
        try:
            if response.status_code != 206:
                raise IncompleteDownloadError(
                    f"server returned HTTP {response.status_code} for range {start}-{end}"
                )
            response.raise_for_status()
            content_range = _parse_content_range(response)
            if content_range is not None:
                range_start, range_end, range_total = content_range
                if (
                    range_start != start
                    or range_end > end
                    or (range_total is not None and range_total != total_size)
                ):
                    raise IncompleteDownloadError(
                        f"unexpected Content-Range: {response.headers.get('Content-Range')}"
                    )

            with partial_path.open("ab") as handle:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    if chunk:
                        handle.write(chunk)
                        if progress_callback:
                            progress_callback(_path_size(partial_path), total_size)
        finally:
            _close_response(response)

    def _download_with_ranges(
        self,
        url: str,
        destination: Path,
        partial_path: Path,
        total_size: int,
        header: dict,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        if partial_path.exists() and partial_path.stat().st_size > total_size:
            partial_path.unlink()

        segment_bytes = download_segment_bytes()
        max_attempts = download_retries() + 1
        last_error = None

        while _path_size(partial_path) < total_size:
            segment_start = _path_size(partial_path)
            segment_end = min(segment_start + segment_bytes - 1, total_size - 1)
            attempt = 1

            while True:
                current_size = _path_size(partial_path)
                if current_size >= segment_end + 1:
                    break

                range_start = current_size
                try:
                    self._append_download_range(
                        url,
                        partial_path,
                        range_start,
                        segment_end,
                        total_size,
                        header,
                        progress_callback,
                    )
                    downloaded_size = _path_size(partial_path)
                    if downloaded_size < segment_end + 1:
                        raise IncompleteDownloadError(
                            f"bytes {range_start}-{segment_end} incomplete: "
                            f"{downloaded_size}/{segment_end + 1}"
                        )
                    break
                except (requests.RequestException, OSError, IncompleteDownloadError) as error:
                    last_error = error
                    downloaded_size = _path_size(partial_path)
                    print(
                        f"[下载] 分段重试 {attempt}/{max_attempts}, "
                        f"range={range_start}-{segment_end}, "
                        f"进度={downloaded_size}/{total_size}, 错误: {error}"
                    )
                    if downloaded_size >= segment_end + 1:
                        break
                    if attempt >= max_attempts:
                        raise RuntimeError(
                            "视频分段下载中断，"
                            f"当前进度 {downloaded_size}/{total_size} 字节，"
                            f"分段已重试 {download_retries()} 次仍未完成"
                        ) from error
                    attempt += 1
                    time.sleep(min(2 ** (attempt - 2), 5))

        if not partial_path.exists() or partial_path.stat().st_size != total_size:
            detail = f": {last_error}" if last_error is not None else ""
            raise RuntimeError(f"视频下载结果大小异常{detail}")

        os.replace(partial_path, destination)
        return destination

    def _download_video(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial_path = destination.with_suffix(f"{destination.suffix}.part")
        header = self._download_headers(url)
        total_size, supports_ranges = self._fetch_download_metadata(url, header)

        if total_size is not None and supports_ranges:
            return self._download_with_ranges(
                url,
                destination,
                partial_path,
                total_size,
                header,
                progress_callback,
            )

        print(f"[下载] 源站不支持Range或无法获取大小，降级整文件下载: total={total_size}")
        return self._download_without_ranges(
            url,
            destination,
            partial_path,
            header,
            progress_callback,
        )

    def _probe_media_file(self, media_path: str | Path) -> dict[str, Any]:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(f"未找到 ffprobe，无法校验媒体文件: {error}") from error

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise RuntimeError(f"媒体文件校验失败: {stderr[-300:] or '未知错误'}")

        try:
            return json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as error:
            raise RuntimeError(f"媒体文件校验结果解析失败: {error}") from error

    def _extract_duration_seconds(self, probe_payload: dict[str, Any]) -> float:
        format_data = probe_payload.get("format")
        if not isinstance(format_data, dict):
            return 0.0
        try:
            return float(format_data.get("duration"))
        except (TypeError, ValueError):
            return 0.0

    def _has_stream(self, probe_payload: dict[str, Any], codec_type: str) -> bool:
        streams = probe_payload.get("streams")
        if not isinstance(streams, list):
            return False
        return any(
            isinstance(stream, dict) and stream.get("codec_type") == codec_type
            for stream in streams
        )

    def validate_video_file(self, video_path: str | Path):
        path = Path(video_path)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("视频下载失败，未生成有效文件")

        payload = self._probe_media_file(path)
        duration = self._extract_duration_seconds(payload)
        if duration <= 1:
            raise RuntimeError(f"视频下载结果异常，时长过短: {duration:.2f}s")
        if not self._has_stream(payload, "video"):
            raise RuntimeError("视频下载结果异常，未检测到视频流")
        if not self._has_stream(payload, "audio"):
            raise RuntimeError("视频下载结果异常，未检测到音频流")

    def validate_mp3_file(self, mp3_path: str | Path):
        path = Path(mp3_path)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("MP3 文件未生成或为空")

        payload = self._probe_media_file(path)
        duration = self._extract_duration_seconds(payload)
        if duration <= 1:
            raise RuntimeError(f"MP3 文件时长异常，当前仅 {duration:.2f}s")
        if not self._has_stream(payload, "audio"):
            raise RuntimeError("MP3 文件异常，未检测到音频流")
    
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
        path = Path(filepath)
        
        # 如果文件已存在，先校验，避免半截文件被当成成功结果
        if path.exists():
            try:
                self.validate_video_file(path)
                print(f"[下载] 文件已存在且校验通过: {filename}")
                return filepath
            except Exception as error:
                print(f"[下载] 已存在文件校验失败，重新下载: {error}")
                path.unlink(missing_ok=True)
        
        print(f"[下载] 选择清晰度: {quality}")
        print(f"[下载] 开始下载: {filename}")
        
        last_reported_percent = 0

        def report_progress(downloaded, total):
            nonlocal last_reported_percent
            if not progress_callback or total <= 0:
                return
            current_percent = int((downloaded / total) * 100)
            if current_percent - last_reported_percent >= 5 or current_percent == 100:
                progress_callback(downloaded, total)
                last_reported_percent = current_percent

        self._download_video(url, path, report_progress)
        self.validate_video_file(path)
        downloaded = path.stat().st_size
        
        print(f"[下载] 完成: {filename} ({downloaded/1024/1024:.2f} MB)")
        return filepath
    
    def get_media_duration(self, media_path: str | Path) -> float:
        payload = self._probe_media_file(media_path)
        duration = self._extract_duration_seconds(payload)
        if duration <= 0:
            raise RuntimeError("无法获取媒体时长，无法执行裁剪")
        return duration

    def _build_audio_filter(
        self,
        duration: float,
        clip_start: int,
        clip_end: int,
        repeat_count: int,
    ) -> tuple[str, str]:
        clip_start = max(int(clip_start), 0)
        clip_end = max(int(clip_end), 0)
        repeat_count = max(int(repeat_count), 1)

        clean_end = duration - clip_end if clip_end else None
        if clean_end is not None and clean_end <= clip_start + 1:
            raise RuntimeError(
                "裁剪时间超过媒体长度，"
                f"媒体时长 {duration:.2f}s，前裁 {clip_start}s，后裁 {clip_end}s"
            )
        if clean_end is None and duration <= clip_start + 1:
            raise RuntimeError(
                f"裁剪后音频过短，媒体时长 {duration:.2f}s，前裁 {clip_start}s"
            )

        trim_args = [f"start={clip_start}"]
        if clean_end is not None:
            trim_args.append(f"end={clean_end:.3f}")
        trim_filter = f"atrim={':'.join(trim_args)},asetpts=PTS-STARTPTS"

        if repeat_count <= 1:
            return f"[0:a]{trim_filter}[outa]", f"{clean_end:.2f}s" if clean_end else "结尾"

        split_labels = "".join(f"[a{index}]" for index in range(repeat_count))
        concat_inputs = "".join(f"[a{index}]" for index in range(repeat_count))
        filter_complex = (
            f"[0:a]{trim_filter},asplit={repeat_count}{split_labels};"
            f"{concat_inputs}concat=n={repeat_count}:v=0:a=1[outa]"
        )
        return filter_complex, f"{clean_end:.2f}s" if clean_end else "结尾"

    def clip_and_convert(
        self, 
        input_path: str, 
        output_name: str,
        clip_start: int = 5,  # 默认剪掉前5秒
        clip_end: int = 3,  # 默认剪掉末尾3秒
        repeat_count: int = 2,  # 默认把纯净音频重复拼接2遍
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        使用FFmpeg剪辑并转换为MP3
        :param input_path: 输入视频路径
        :param output_name: 输出文件名（不含扩展名）
        :param clip_start: 开始时间（秒），默认5秒跳过广告
        :param clip_end: 末尾裁剪时间（秒），默认3秒
        :param repeat_count: 纯净音频重复拼接次数，默认2遍
        :return: MP3文件路径
        """
        output_path = os.path.join(self.download_dir, f"{output_name}.mp3")
        output_file = Path(output_path)
        partial_output = output_file.with_name(
            f".{output_file.stem}.{os.getpid()}.{int(time.time() * 1000)}"
            f"{output_file.suffix}.part"
        )

        partial_output.unlink(missing_ok=True)
        duration = self.get_media_duration(input_path)
        filter_complex, clean_end_text = self._build_audio_filter(
            duration,
            clip_start,
            clip_end,
            repeat_count,
        )
        
        # 构建FFmpeg命令
        # filter_complex: 裁剪前后广告，并按需把纯净音频重复拼接
        # -vn: 禁用视频
        # -ar 44100: 音频采样率
        # -ac 2: 双声道
        # -b:a 192k: 比特率
        cmd = [
            'ffmpeg',
            '-y',  # 覆盖输出文件
            '-i', input_path,  # 输入文件
            '-filter_complex', filter_complex,
            '-map', '[outa]',
            '-vn',  # 不要视频
            '-ar', '44100',  # 采样率
            '-ac', '2',  # 声道数
            '-b:a', '192k',  # 音频比特率
            '-f', 'mp3',  # 输出格式
            str(partial_output)
        ]
        
        print(f"[转换] FFmpeg剪辑并转MP3: {output_name}.mp3")
        print(
            f"[转换] 前裁 {clip_start} 秒，后裁 {clip_end} 秒，"
            f"纯净段结束: {clean_end_text}，重复拼接 x{max(int(repeat_count), 1)}"
        )
        
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
            
            self.validate_mp3_file(partial_output)
            os.replace(partial_output, output_file)

            if progress_callback:
                progress_callback(100)
            
            print(f"[转换] 完成: {output_name}.mp3")
            return output_path
            
        except subprocess.CalledProcessError as e:
            partial_output.unlink(missing_ok=True)
            print(f"[转换] FFmpeg错误: {e.stderr}")
            raise RuntimeError(f"FFmpeg转换失败: {e.stderr}")
        except Exception:
            partial_output.unlink(missing_ok=True)
            raise
    
    def process_pipeline(
        self,
        url_or_vid: str,
        skip_seconds: int = 5,  # 默认跳过前5秒广告
        trim_end_seconds: int = 3,  # 默认剪掉末尾3秒广告
        repeat_count: int = 2,  # 默认纯净音频重复拼接2遍
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
                percent = int(30 + (downloaded / total) * 40)  # 30-70% 范围
                progress_callback("download", percent)
        
        video_path = self.download(info, download_progress)
        result["video_path"] = video_path
        
        if task_check and not task_check():
            raise RuntimeError("任务已取消")
        
        # 3. 剪辑并转MP3
        if progress_callback:
            progress_callback("convert", 80)
        
        # 生成输出文件名
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", info["name"])
        repeat_suffix = f"_x{repeat_count}" if repeat_count > 1 else ""
        output_name = f"{safe_name}{repeat_suffix}"
        mp3_path = self.clip_and_convert(
            video_path, 
            output_name,
            clip_start=skip_seconds,
            clip_end=trim_end_seconds,
            repeat_count=repeat_count,
        )
        
        result["mp3_path"] = mp3_path
        result["mp3_filename"] = os.path.basename(mp3_path)
        result["title"] = info["name"]
        result["skip_seconds"] = skip_seconds
        result["trim_end_seconds"] = trim_end_seconds
        result["repeat_count"] = repeat_count
        
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
