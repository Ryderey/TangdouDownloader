#!/usr/bin/env python3
"""
路径一致性诊断脚本
用于检查 TaskStore 和 VideoDownloader 是否使用相同的目录
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_paths():
    print("=" * 60)
    print("路径一致性诊断")
    print("=" * 60)
    
    # 环境信息
    print("\n[环境信息]")
    print(f"当前工作目录: {os.getcwd()}")
    print(f"脚本所在目录: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"Python路径: {sys.executable}")
    
    # 检查项目根目录
    print("\n[项目根目录检测]")
    possible_paths = [
        os.getcwd(),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '/home/ryl/script/tangdou-web',
        '/home/ryl/tangdou-mp3',
    ]
    
    for path in possible_paths:
        app_py = os.path.join(path, 'app.py')
        exists = os.path.exists(app_py)
        print(f"  {path}: {'✓' if exists else '✗'} app.py")
    
    # 导入并检查各个组件
    print("\n[组件路径检查]")
    
    try:
        from tasks.processor import TaskStore
        store = TaskStore()
        print(f"TaskStore.data_dir: {store.data_dir}")
        print(f"TaskStore.tasks_dir: {store.tasks_dir}")
        print(f"  目录存在: {os.path.exists(store.data_dir)}")
        
        # 检查现有任务
        if os.path.exists(store.tasks_dir):
            task_files = [f for f in os.listdir(store.tasks_dir) if f.endswith('.json')]
            print(f"  现有任务数: {len(task_files)}")
            if task_files:
                print(f"  示例任务: {task_files[:3]}")
    except Exception as e:
        print(f"TaskStore 错误: {e}")
    
    try:
        from modules.downloader import VideoDownloader
        downloader = VideoDownloader()
        print(f"VideoDownloader.download_dir: {downloader.download_dir}")
        print(f"  目录存在: {os.path.exists(downloader.download_dir)}")
        
        # 检查现有MP3
        if os.path.exists(downloader.download_dir):
            mp3_files = [f for f in os.listdir(downloader.download_dir) if f.endswith('.mp3')]
            print(f"  现有MP3数: {len(mp3_files)}")
            if mp3_files:
                print(f"  示例MP3: {mp3_files[:3]}")
    except Exception as e:
        print(f"VideoDownloader 错误: {e}")
    
    # 检查一致性
    print("\n[一致性检查]")
    try:
        from tasks.processor import TaskStore
        from modules.downloader import VideoDownloader
        
        store = TaskStore()
        downloader = VideoDownloader()
        
        if store.data_dir == downloader.download_dir:
            print("✓ 目录一致")
        else:
            print("✗ 目录不一致!")
            print(f"  TaskStore: {store.data_dir}")
            print(f"  VideoDownloader: {downloader.download_dir}")
    except Exception as e:
        print(f"检查失败: {e}")
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)

if __name__ == "__main__":
    check_paths()
