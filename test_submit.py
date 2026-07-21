#!/usr/bin/env python3
"""测试脚本：直接测试后端 API，绕过前端"""

import requests
import sys
import time

BASE_URL = "http://localhost:18080"
TEST_URL = "https://www.tangdouddn.com/h5/play?vid=20000011230835"

print("Test URL: {}".format(BASE_URL))
print("Test video: {}".format(TEST_URL))
print("-" * 50)

# 1. 测试首页
print("\n[1] Testing index page...")
try:
    r = requests.get(f"{BASE_URL}/", timeout=5)
    print("    Status: {}".format(r.status_code))
except Exception as e:
    print("    Error: {}".format(e))
    sys.exit(1)

# 2. 测试视频信息接口
print("\n[2] Testing video info API...")
try:
    r = requests.post(f"{BASE_URL}/api/video-info", 
        json={"url": TEST_URL},
        timeout=10
    )
    print("    Status: {}".format(r.status_code))
    print("    Response: {}".format(r.text[:200]))
except Exception as e:
    print("    Error: {}".format(e))

# 3. 测试提交任务
print("\n[3] Testing task submission...")
try:
    r = requests.post(f"{BASE_URL}/api/submit",
        json={"url": TEST_URL, "skip_time": "5"},
        timeout=10
    )
    print("    Status: {}".format(r.status_code))
    print("    Response: {}".format(r.text))
    
    result = r.json()
    if result.get("success") and result.get("task_id"):
        task_id = result["task_id"]
        print("    Task ID: {}".format(task_id))
        
        # 4. 轮询任务状态
        print("\n[4] Polling task status...")
        for i in range(10):
            time.sleep(1)
            r = requests.get(f"{BASE_URL}/api/status/{task_id}", timeout=5)
            status = r.json()
            task = status.get('task', {})
            print(f"    [{i+1}] {task.get('status')} - {task.get('message')}")
            
            if task.get('status') in ['completed', 'failed']:
                if task.get('error'):
                    print("\n    Error detail: {}".format(task.get('error')))
                break
    else:
        print("    Submit failed: {}".format(result.get('error')))
except Exception as e:
    print("    Error: {}".format(e))
    import traceback
    traceback.print_exc()

print("\n" + "-" * 50)
print("Test complete")
