#!/usr/bin/env python3
"""测试脚本：直接测试后端 API，绕过前端"""

import requests
import sys
import time

BASE_URL = "http://localhost:18080"
TEST_URL = "https://www.tangdouddn.com/h5/play?vid=20000011230835"

print(f"测试地址: {BASE_URL}")
print(f"测试视频: {TEST_URL}")
print("-" * 50)

# 1. 测试首页
print("\n[1] 测试首页...")
try:
    r = requests.get(f"{BASE_URL}/", timeout=5)
    print(f"    状态: {r.status_code}")
except Exception as e:
    print(f"    错误: {e}")
    sys.exit(1)

# 2. 测试视频信息接口
print("\n[2] 测试获取视频信息...")
try:
    r = requests.post(f"{BASE_URL}/api/video-info", 
        json={"url": TEST_URL},
        timeout=10
    )
    print(f"    状态: {r.status_code}")
    print(f"    响应: {r.text[:200]}")
except Exception as e:
    print(f"    错误: {e}")

# 3. 测试提交任务
print("\n[3] 测试提交任务...")
try:
    r = requests.post(f"{BASE_URL}/api/submit",
        json={"url": TEST_URL, "skip_time": "5"},
        timeout=10
    )
    print(f"    状态: {r.status_code}")
    print(f"    响应: {r.text}")
    
    result = r.json()
    if result.get("success") and result.get("task_id"):
        task_id = result["task_id"]
        print(f"    任务ID: {task_id}")
        
        # 4. 轮询任务状态
        print("\n[4] 查询任务状态...")
        for i in range(10):
            time.sleep(1)
            r = requests.get(f"{BASE_URL}/api/status/{task_id}", timeout=5)
            status = r.json()
            task = status.get('task', {})
            print(f"    [{i+1}] {task.get('status')} - {task.get('message')}")
            
            if task.get('status') in ['completed', 'failed']:
                if task.get('error'):
                    print(f"\n    错误详情: {task.get('error')}")
                break
    else:
        print(f"    提交失败: {result.get('error')}")
except Exception as e:
    print(f"    错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "-" * 50)
print("测试完成")
