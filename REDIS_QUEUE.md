# Redis Queue 架构说明

## 概述

项目使用 **Redis + RQ** 架构，解决多进程环境下任务状态不一致的问题。Web 进程只负责提交和查询任务，下载与转换由独立 Worker 消费队列。

当前实现还包含：

- 任务状态 Redis + 本地 JSON 双写，本地路径为 `static/downloads/.tasks/`
- Redis 不可用时 `/api/status/<task_id>` 回退读取本地 JSON
- Redis 不可用时 `/api/submit` 返回 HTTP `503`，不创建新任务
- 同一视频和相同处理参数在保留期内重复提交返回 HTTP `409`
- 默认保留时间 3 小时，可用 `TANGDOU_RETENTION_HOURS` 覆盖
- Worker 启动时自动扫描本地未完成任务并恢复入队

## 架构图

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│   Gunicorn  │────▶│    Redis    │
└─────────────┘     │  (2 workers)│     │   (Queue)   │
                    └─────────────┘     └──────┬──────┘
                                                │
                           ┌────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ RQ Worker   │
                    │ (处理任务)  │
                    └─────────────┘
```

## 组件说明

### 1. Web服务 (Gunicorn)
- 监听 0.0.0.0:18080
- 2个worker处理HTTP请求
- 负责：接收任务提交、查询状态、提供API
- **不处理实际下载任务**

### 2. Redis
- 存储 RQ 队列
- 存储任务状态和去重键
- 默认端口 6379

### 3. RQ Worker
- 独立进程运行
- 从队列取任务并处理
- 负责：视频下载、转MP3、更新状态
- 默认 1 个 worker
- 通过 `.venv/bin/python scripts/rq_worker.py` 启动，避免 RQ CLI 参数版本差异

## 安装部署

### 方式一：自动部署（推荐）

```bash
cd /home/ryl/script/tangdou-web
chmod +x scripts/deploy_redis_queue.sh
./scripts/deploy_redis_queue.sh
```

### 方式二：手动部署

#### 1. 安装Redis
```bash
sudo apt-get update
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

#### 2. 安装Python依赖
```bash
cd /home/ryl/script/tangdou-web
source .venv/bin/activate
pip install redis rq
```

#### 3. 安装服务
```bash
# 复制服务文件
cp scripts/tangdou-mp3.service ~/.config/systemd/user/
cp scripts/tangdou-worker.service ~/.config/systemd/user/
cp scripts/tangdou-cleanup.service ~/.config/systemd/user/
cp scripts/tangdou-cleanup.timer ~/.config/systemd/user/

# 重新加载配置
systemctl --user daemon-reload

# 启动服务
systemctl --user start tangdou-mp3
systemctl --user start tangdou-worker
systemctl --user start tangdou-cleanup.timer

# 设置开机自启
systemctl --user enable tangdou-mp3
systemctl --user enable tangdou-worker
systemctl --user enable tangdou-cleanup.timer
```

## 管理命令

### 服务管理
```bash
# 查看状态
systemctl --user status tangdou-mp3
systemctl --user status tangdou-worker
systemctl --user status tangdou-cleanup.timer

# 重启服务
systemctl --user restart tangdou-mp3
systemctl --user restart tangdou-worker

# 查看日志
journalctl --user -u tangdou-mp3 -f
journalctl --user -u tangdou-worker -f
journalctl --user -u tangdou-cleanup.service -f
```

### 队列管理
```bash
# 查看队列统计
curl http://localhost:18080/api/queue-stats

# 查看Redis中的任务
redis-cli
> keys tangdou:task:*
> smembers tangdou:task_ids
> keys tangdou:dedupe:*
```

### 手动运行Worker（调试用）
```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/rq_worker.py
```

## 新API接口

### 队列统计
```bash
GET /api/queue-stats

响应:
{
    "success": true,
    "queue": {
        "queued": 0,     # 等待处理的任务数
        "started": 1,    # 正在处理的任务数
        "finished": 10,  # 已完成的任务数
        "failed": 0,     # 失败的任务数
        "redis_available": true,
        "worker_count": 1,
        "worker_names": ["tangdou-worker-host"],
        "workers_visible": true
    }
}
```

### 提交任务

Redis 不可用时：

```json
{"error": "Redis不可用，任务未提交"}
```

重复任务：

```json
{"duplicate": true, "existing_task_id": "...", "status": "completed", "error": "重复任务"}
```

默认音频处理参数为前裁 5 秒、后裁 3 秒、重复拼接 x2。去重键包含 `vid`、前裁秒数、后裁秒数和重复次数。

## 故障排查

### 1. Web服务启动失败
```bash
# 检查Redis连接
redis-cli ping

# 检查日志
journalctl --user -u tangdou-mp3 -n 50
```

### 2. Worker不处理任务
```bash
# 检查Worker是否运行
systemctl --user status tangdou-worker

# 检查队列是否有任务
redis-cli llen rq:queue:tangdou

# 手动启动Worker查看错误
.venv/bin/python scripts/rq_worker.py
```

### 3. 任务一直显示"等待处理"
```bash
# 检查Worker是否连接到正确的队列
redis-cli keys rq:worker:*

# 重启Worker
systemctl --user restart tangdou-worker
```

### 4. 误判重复任务

先查看重复任务状态：

```bash
curl http://localhost:18080/api/tasks
redis-cli --scan --pattern 'tangdou:dedupe:*'
```

确认需要释放某个任务的去重键：

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/cleanup_redis.py --release-task <task_id>
.venv/bin/python scripts/cleanup_redis.py --release-task <task_id> --yes
```

### 5. 手动清理 Redis 缓存

脚本默认 dry-run，只有加 `--yes` 才删除：

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/cleanup_redis.py --help
.venv/bin/python scripts/cleanup_redis.py --stale-dedupe --yes
.venv/bin/python scripts/cleanup_redis.py --state --yes
```

清理 RQ 队列前建议先停 Worker：

```bash
systemctl --user stop tangdou-worker
.venv/bin/python scripts/cleanup_redis.py --rq --yes
systemctl --user start tangdou-worker
```

### 6. 手动清理过时文件

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/cleanup.py
.venv/bin/python scripts/cleanup.py --max-age-hours 0
.venv/bin/python scripts/cleanup.py --max-age-hours 0 --keep-mp3
```

## 回滚到文件队列（方案2）

如果Redis方案有问题，可以回滚到单进程模式：

```bash
# 1. 停止服务
systemctl --user stop tangdou-worker
systemctl --user stop tangdou-mp3

# 2. 禁用worker服务
systemctl --user disable tangdou-worker

# 3. 恢复单进程配置
# 编辑 ~/.config/systemd/user/tangdou-mp3.service
# 将 --workers 2 改为 --workers 1

# 4. 启动服务
systemctl --user start tangdou-mp3
```

## 性能调优

### 增加Worker数量
复制一份 `tangdou-worker.service` 为不同服务名，保持 `ExecStart=/home/ryl/script/tangdou-web/.venv/bin/python /home/ryl/script/tangdou-web/scripts/rq_worker.py`。不要使用旧 RQ CLI 参数。

### Redis持久化
如需重启后保留任务，编辑 `/etc/redis/redis.conf`：
```
save 900 1
save 300 10
save 60 10000
appendonly yes
```

然后重启Redis：
```bash
sudo systemctl restart redis-server
```
