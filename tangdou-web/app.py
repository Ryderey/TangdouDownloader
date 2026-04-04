"""
糖豆视频下载 Web 应用
Flask + FFmpeg + Tailscale
"""

import os
import sys
import re

# 添加当前目录到路径，确保能导入 modules 和 tasks
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, send_from_directory

from tasks.processor import get_processor, TaskProcessor

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tangdou-web-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 初始化任务处理器
processor = get_processor()


def parse_time(time_str: str) -> int:
    """
    解析时间字符串为秒数
    支持格式: 秒、分:秒、时:分:秒
    :return: 秒数
    """
    if not time_str or not time_str.strip():
        return 5  # 默认5秒
    
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
    
    return 5  # 默认5秒


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
    
    # 解析跳过时间（默认5秒）
    skip_seconds = 5
    if data.get('skip_time'):
        try:
            skip_seconds = parse_time(data.get('skip_time'))
        except:
            skip_seconds = 5
    
    # 限制范围
    skip_seconds = max(0, min(skip_seconds, 300))  # 0-300秒
    
    try:
        task_id = processor.submit(url, skip_seconds)
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '任务已提交'
        })
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
    """手动触发清理"""
    try:
        count = processor.cleanup_old_files(max_age_hours=0)  # 立即清理所有
        return jsonify({
            'success': True, 
            'message': f'已清理 {count} 个文件'
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
    # 开发模式
    app.run(host='0.0.0.0', port=5000, debug=True)
