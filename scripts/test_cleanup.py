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
    print("MP3 auto-cleanup test")
    print("=" * 60)
    
    # 初始化存储
    store = TaskStore()
    print("\n[1] Task store dir: {}".format(store.tasks_dir))
    print("[1] Download dir: {}".format(store.data_dir))
    
    # 创建测试文件
    print("\n[2] Creating test task and MP3 file...")
    
    # 创建一个模拟的已完成任务
    test_task_id = "test_cleanup_001"
    test_mp3_filename = "test_cleanup_001.mp3"
    test_mp3_path = os.path.join(store.data_dir, test_mp3_filename)
    
    # 创建模拟MP3文件
    with open(test_mp3_path, 'w') as f:
        f.write("dummy mp3 content")
    print("[2] Created test MP3: {}".format(test_mp3_path))
    
    # 创建任务JSON文件（模拟1小时前的任务）
    task_data = {
        'id': test_task_id,
        'url': 'http://test.com',
        'skip_seconds': 5,
        'status': 'completed',
        'progress': 100,
        'message': 'Processing complete',
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
    print("[2] Created task file: {}".format(task_file))
    
    # 修改文件时间为2小时前
    os.utime(task_file, (time.time() - 7200, time.time() - 7200))
    os.utime(test_mp3_path, (time.time() - 7000, time.time() - 7000))
    
    # 测试清理（保留1小时，应该清理掉2小时前的文件）
    print("\n[3] Running cleanup (retain 1 hour)...")
    cleaned = store.cleanup_old(max_age_hours=1, delete_mp3=True)
    print("[3] Cleanup complete, {} files cleaned".format(cleaned))
    
    # 验证结果
    print("\n[4] Verifying cleanup result...")
    task_exists = os.path.exists(task_file)
    mp3_exists = os.path.exists(test_mp3_path)
    
    if not task_exists and not mp3_exists:
        print("[4] OK - Task file and MP3 file both cleaned")
    else:
        print("[4] FAIL - Task exists: {}, MP3 exists: {}".format(task_exists, mp3_exists))
    
    # 测试不删除MP3的情况
    print("\n[5] Testing no-delete-MP3 mode...")
    
    # 重新创建文件
    with open(test_mp3_path, 'w') as f:
        f.write("dummy mp3 content")
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)
    os.utime(task_file, (time.time() - 7200, time.time() - 7200))
    
    cleaned = store.cleanup_old(max_age_hours=1, delete_mp3=False)
    print("[5] Cleanup complete (JSON only), {} files cleaned".format(cleaned))
    
    task_exists = os.path.exists(task_file)
    mp3_exists = os.path.exists(test_mp3_path)
    
    if not task_exists and mp3_exists:
        print("[5] OK - Task file cleaned, MP3 file retained")
        # 清理测试MP3
        os.remove(test_mp3_path)
    else:
        print("[5] FAIL - Task exists: {}, MP3 exists: {}".format(task_exists, mp3_exists))
    
    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)

if __name__ == "__main__":
    test_cleanup()
