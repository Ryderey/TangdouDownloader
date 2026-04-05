# Redis Queue 架构说明

## 概述

项目已迁移到 **Redis + RQ** 架构，解决多进程环境下任务状态不一致的问题。

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
- 存储任务队列
- 存储任务状态
- 默认端口 6379

### 3. RQ Worker
- 独立进程运行
- 从队列取任务并处理
- 负责：视频下载、转MP3、更新状态
- 可以有多个worker（默认1个）

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

# 重新加载配置
systemctl --user daemon-reload

# 启动服务
systemctl --user start tangdou-mp3
systemctl --user start tangdou-worker

# 设置开机自启
systemctl --user enable tangdou-mp3
systemctl --user enable tangdou-worker
```

## 管理命令

### 服务管理
```bash
# 查看状态
systemctl --user status tangdou-mp3
systemctl --user status tangdou-worker

# 重启服务
systemctl --user restart tangdou-mp3
systemctl --user restart tangdou-worker

# 查看日志
journalctl --user -u tangdou-mp3 -f
journalctl --user -u tangdou-worker -f
```

### 队列管理
```bash
# 查看队列统计
curl http://localhost:18080/api/queue-stats

# 查看Redis中的任务
redis-cli
> keys tangdou:task:*
> smembers tangdou:task_ids
```

### 手动运行Worker（调试用）
```bash
cd /home/ryl/script/tangdou-web
source .venv/bin/activate
rq worker --url redis://localhost:6379/0 --queues tangdou --with-scheduler
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
        "failed": 0      # 失败的任务数
    }
}
```

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
rq worker --url redis://localhost:6379/0 --queues tangdou
```

### 3. 任务一直显示"等待处理"
```bash
# 检查Worker是否连接到正确的队列
redis-cli keys rq:worker:*

# 重启Worker
systemctl --user restart tangdou-worker
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
编辑 `~/.config/systemd/user/tangdou-worker.service`：
```bash
ExecStart=/bin/bash -c 'cd /home/ryl/script/tangdou-web && source .venv/bin/activate && rq worker --url redis://localhost:6379/0 --queues tangdou --with-scheduler & rq worker --url redis://localhost:6379/0 --queues tangdou'
```

或使用 supervisord 管理多个worker。

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
