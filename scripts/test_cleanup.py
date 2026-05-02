#!/usr/bin/env python3
"""
清理功能测试脚本
用于验证MP3自动清理功能是否正常工作
"""

import os
import sys
import time
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks.processor import TaskStore, TaskProcessor

def test_cleanup():
    print("=" * 60)
    print("MP3自动清理功能测试")
    print("=" * 60)
    
    # 初始化存储
    store = TaskStore()
    print(f"\n[1] 任务存储目录: {store.tasks_dir}")
    print(f"[1] 下载目录: {store.data_dir}")
    
    # 创建测试文件
    print("\n[2] 创建测试任务和MP3文件...")
    
    # 创建一个模拟的已完成任务
    test_task_id = "test_cleanup_001"
    test_mp3_filename = "test_cleanup_001.mp3"
    test_mp3_path = os.path.join(store.data_dir, test_mp3_filename)
    
    # 创建模拟MP3文件
    with open(test_mp3_path, 'w') as f:
        f.write("dummy mp3 content")
    print(f"[2] 创建测试MP3: {test_mp3_path}")
    
    # 创建任务JSON文件（模拟1小时前的任务）
    task_data = {
        'id': test_task_id,
        'url': 'http://test.com',
        'skip_seconds': 5,
        'status': 'completed',
        'progress': 100,
        'message': '处理完成',
        'result': {
            'mp3_path': test_mp3_path,
            'mp3_filename': test_mp3_filename,
            'title': 'Test Song'
        },
        'error': '',
        'created_at': time.time() - 7200,  # 2小时前
        'completed_at': time.time() - 7000,
        'logs': []
    }
    
    task_file = os.path.join(store.tasks_dir, f"{test_task_id}.json")
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)
    print(f"[2] 创建任务文件: {task_file}")
    
    # 修改文件时间为2小时前
    os.utime(task_file, (time.time() - 7200, time.time() - 7200))
    os.utime(test_mp3_path, (time.time() - 7000, time.time() - 7000))
    
    # 测试清理（保留1小时，应该清理掉2小时前的文件）
    print("\n[3] 执行清理（保留1小时）...")
    cleaned = store.cleanup_old(max_age_hours=1, delete_mp3=True)
    print(f"[3] 清理完成，共清理 {cleaned} 个文件")
    
    # 验证结果
    print("\n[4] 验证清理结果...")
    task_exists = os.path.exists(task_file)
    mp3_exists = os.path.exists(test_mp3_path)
    
    if not task_exists and not mp3_exists:
        print("[4] OK - 任务文件和MP3文件都已清理")
    else:
        print(f"[4] FAIL - 任务文件存在: {task_exists}, MP3文件存在: {mp3_exists}")
    
    # 测试不删除MP3的情况
    print("\n[5] 测试不删除MP3模式...")
    
    # 重新创建文件
    with open(test_mp3_path, 'w') as f:
        f.write("dummy mp3 content")
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)
    os.utime(task_file, (time.time() - 7200, time.time() - 7200))
    
    cleaned = store.cleanup_old(max_age_hours=1, delete_mp3=False)
    print(f"[5] 清理完成（仅JSON），共清理 {cleaned} 个文件")
    
    task_exists = os.path.exists(task_file)
    mp3_exists = os.path.exists(test_mp3_path)
    
    if not task_exists and mp3_exists:
        print("[5] OK - 任务文件已清理，MP3文件保留")
        # 清理测试MP3
        os.remove(test_mp3_path)
    else:
        print(f"[5] FAIL - 任务文件存在: {task_exists}, MP3文件存在: {mp3_exists}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_cleanup()
