"""
糖豆视频下载 Web 应用
Flask + FFmpeg + Tailscale
"""
from __future__ import annotations

import os
import sys
import re

# 添加当前目录到路径，确保能导入 modules 和 tasks
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, send_from_directory

from tasks.processor import (
    DuplicateTaskError,
    RedisUnavailableError,
    get_processor,
    get_retention_hours,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tangdou-web-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 初始化任务处理器
processor = get_processor()


def parse_time(time_str: str, default: int = 5) -> int:
    """
    解析时间字符串为秒数
    支持格式: 秒、分:秒、时:分:秒
    :return: 秒数
    """
    if not time_str or not time_str.strip():
        return default
    
    parts = re.split(r'[:\s\.,，]+', time_str.strip())
    parts = [p for p in parts if p.isdigit()]
    
    if len(parts) == 1:
        # 只有秒
        return int(parts[0])
    elif len(parts) == 2:
        # 分:秒
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        # 时:分:秒
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    
    return default


def parse_bool(value, default: bool = False) -> bool:
    """解析前端复选框/JSON布尔值。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return default


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    """获取视频信息（用于预览）"""
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': '请输入视频链接'}), 400
    
    try:
        from modules.tangdou import VideoAPI
        api = VideoAPI()
        info = api.get_video_info(url)
        
        # 选择最低清晰度
        qualities = list(info['urls'].keys())
        lowest_quality = None
        for q in ['V360P', 'H360P', 'V540P', 'H540P', 'unknown']:
            if q in qualities:
                lowest_quality = q
                break
        
        return jsonify({
            'success': True,
            'title': info['name'],
            'quality': lowest_quality or qualities[0] if qualities else 'unknown'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/submit', methods=['POST'])
def submit_task():
    """提交处理任务"""
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': '请输入视频链接'}), 400
    
    skip_start_enabled = parse_bool(data.get('skip_start_enabled'), default=True)
    trim_end_enabled = parse_bool(data.get('trim_end_enabled'), default=True)
    repeat_concat_enabled = parse_bool(data.get('repeat_concat_enabled'), default=True)

    try:
        skip_seconds = parse_time(data.get('skip_time'), default=5) if skip_start_enabled else 0
    except Exception:
        skip_seconds = 5 if skip_start_enabled else 0

    try:
        trim_end_seconds = parse_time(data.get('trim_end_time'), default=3) if trim_end_enabled else 0
    except Exception:
        trim_end_seconds = 3 if trim_end_enabled else 0

    repeat_count = 2 if repeat_concat_enabled else 1

    # 限制范围
    skip_seconds = max(0, min(skip_seconds, 300))
    trim_end_seconds = max(0, min(trim_end_seconds, 300))
    
    try:
        task_id = processor.submit(
            url,
            skip_seconds=skip_seconds,
            trim_end_seconds=trim_end_seconds,
            repeat_count=repeat_count,
        )
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '任务已提交'
        })
    except RedisUnavailableError:
        return jsonify({'error': 'Redis不可用，任务未提交'}), 503
    except DuplicateTaskError as e:
        return jsonify({
            'duplicate': True,
            'existing_task_id': e.existing_task_id,
            'status': e.status,
            'error': '重复任务'
        }), 409
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status/<task_id>')
def task_status(task_id):
    """查询任务状态"""
    task = processor.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    return jsonify({
        'success': True,
        'task': task.to_dict()
    })


@app.route('/api/download/<path:filename>')
def download_file(filename):
    """下载文件"""
    # 安全检查：防止目录遍历
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': '非法文件名'}), 400
    
    directory = os.path.join(app.root_path, 'static/downloads')
    
    # 检查文件是否存在
    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在或已过期'}), 404
    
    return send_from_directory(
        directory, 
        filename, 
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/tasks')
def list_tasks():
    """获取最近的任务列表"""
    tasks = processor.get_all_tasks(limit=20)
    return jsonify({
        'success': True,
        'tasks': [t.to_dict() for t in tasks]
    })


@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """手动触发清理 - 默认保留3小时，可由环境变量覆盖"""
    try:
        data = request.get_json() or {}
        # 获取清理时间（小时），默认3小时，0表示清理所有
        max_age_hours = data.get('max_age_hours', get_retention_hours())
        
        count = processor.cleanup_old_files(max_age_hours=max_age_hours)
        
        if max_age_hours == 0:
            message = f'已清理所有历史文件，共 {count} 个'
        else:
            message = f'已清理 {max_age_hours} 小时前的文件，共 {count} 个'
        
        return jsonify({
            'success': True, 
            'message': message,
            'cleaned_count': count,
            'max_age_hours': max_age_hours
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/storage-info', methods=['GET'])
def storage_info():
    """获取存储使用情况"""
    try:
        import os
        
        download_dir = os.path.join(app.root_path, 'static/downloads')
        
        # 计算目录大小
        total_size = 0
        mp3_count = 0
        task_count = 0
        
        if os.path.exists(download_dir):
            for root, dirs, files in os.walk(download_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        size = os.path.getsize(filepath)
                        total_size += size
                        if file.endswith('.mp3'):
                            mp3_count += 1
                        elif file.endswith('.json'):
                            task_count += 1
                    except:
                        pass
        
        # 转换大小为可读格式
        def format_size(size_bytes):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024
            return f"{size_bytes:.2f} TB"
        
        return jsonify({
            'success': True,
            'total_size_bytes': total_size,
            'total_size_formatted': format_size(total_size),
            'mp3_count': mp3_count,
            'task_count': task_count,
            'download_dir': download_dir
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/queue-stats', methods=['GET'])
def queue_stats():
    """获取队列统计信息"""
    try:
        stats = processor.get_queue_stats()
        return jsonify({
            'success': True,
            'queue': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    """404错误处理"""
    if request.path.startswith('/api/'):
        return jsonify({'error': '接口不存在'}), 404
    return render_template('index.html'), 404


@app.errorhandler(500)
def internal_error(e):
    """500错误处理"""
    return jsonify({'error': '服务器内部错误'}), 500


if __name__ == '__main__':
    # 开发模式: python app.py
    # 生产模式: python wsgi.py (使用 waitress)
    import argparse
    parser = argparse.ArgumentParser(description='糖豆MP3提取器')
    parser.add_argument('--prod', action='store_true', help='使用waitress生产模式启动')
    parser.add_argument('--port', type=int, default=5000, help='端口号')
    args = parser.parse_args()

    if args.prod:
        from waitress import serve
        print("[生产模式] http://0.0.0.0:{}".format(args.port))
        serve(app, host='0.0.0.0', port=args.port, threads=4)
    else:
        print("[开发模式] http://0.0.0.0:{}".format(args.port))
        app.run(host='0.0.0.0', port=args.port, debug=True)
