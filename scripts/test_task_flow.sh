#!/bin/bash
# 测试任务流程是否正常

API_URL="http://100.99.106.60:18080"
TEST_URL="https://www.tangdouddn.com/h5/play?"\
"hash=b44a7b8767a79b2b729305b4b65691ae&vid=20000011230835&utm_campaign=client_down&utm_source=tangdou_android&utm_medium=wx_chat&utm_type=0&share_uid=19388923" 

echo "=========================================="
echo "  任务流程测试"
echo "=========================================="
echo ""
echo "API地址: $API_URL"
echo ""

# 1. 检查服务状态
echo "[1] 检查服务状态..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/")
if [ "$STATUS" != "200" ]; then
    echo "✗ 服务不可用 (HTTP $STATUS)"
    exit 1
fi
echo "✓ 服务正常"

# 2. 提交测试任务
echo ""
echo "[2] 提交测试任务..."
RESPONSE=$(curl -s -X POST "$API_URL/api/submit" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"$TEST_URL\", \"skip_time\": \"5\"}")

echo "响应: $RESPONSE"

TASK_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('task_id', ''))" 2>/dev/null)

if [ -z "$TASK_ID" ]; then
    echo "✗ 未能获取任务ID"
    exit 1
fi

echo "✓ 任务ID: $TASK_ID"

# 3. 立即查询任务状态（测试是否存在）
echo ""
echo "[3] 立即查询任务状态..."
STATUS_RESPONSE=$(curl -s "$API_URL/api/status/$TASK_ID")
echo "状态响应: $STATUS_RESPONSE"

# 使用Python解析JSON检查是否有错误
HAS_ERROR=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('error') else 'no')" 2>/dev/null || echo "parse_error")

if [ "$HAS_ERROR" = "yes" ]; then
    echo "✗ 任务查询失败!"
    echo ""
    echo "可能的修复方案:"
    echo "  1. 检查 static/downloads/.tasks/ 目录权限"
    echo "  2. 重启服务: systemctl --user restart tangdou-mp3"
    echo "  3. 运行诊断: python3 scripts/check_paths.py"
    exit 1
else
    echo "✓ 任务存在"
fi

# 4. 轮询等待完成
echo ""
echo "[4] 等待任务完成（最多60秒）..."
for i in {1..30}; do
    STATUS_RESPONSE=$(curl -s "$API_URL/api/status/$TASK_ID")
    TASK_STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('task', {}).get('status', ''))" 2>/dev/null)
    
    echo "  第 $i 次检查: $TASK_STATUS"
    
    if [ "$TASK_STATUS" = "completed" ]; then
        echo "✓ 任务完成!"
        echo "结果:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
        exit 0
    elif [ "$TASK_STATUS" = "failed" ]; then
        echo "✗ 任务失败!"
        echo "错误详情:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
        exit 1
    fi
    
    sleep 2
done

echo "✗ 等待超时"
exit 1
