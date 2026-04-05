# UV 环境部署指南

针对使用 `uv` 管理虚拟环境的部署说明。

## 前置条件

1. **uv 已安装**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.cargo/env
   ```

2. **虚拟环境已创建**
   ```bash
   cd /home/ryl/script/tangdou-web
   uv venv
   ```

3. **基础依赖已安装**
   ```bash
   uv pip install -r requirements.txt
   ```

## 快速部署

### 步骤1：运行部署前检查

```bash
cd /home/ryl/script/tangdou-web
chmod +x scripts/deploy_check.sh
./scripts/deploy_check.sh
```

### 步骤2：执行部署

```bash
# 方式一：自动部署
chmod +x scripts/deploy_redis_queue.sh
./scripts/deploy_redis_queue.sh

# 方式二：手动部署（如果自动部署失败）
```

### 步骤3：手动部署（备用）

```bash
cd /home/ryl/script/tangdou-web

# 1. 安装 Redis
sudo apt-get update
sudo apt-get install -y redis-server
sudo systemctl enable redis-server --now

# 2. 安装 Python 依赖（使用 uv）
uv pip install redis rq

# 3. 验证依赖
.venv/bin/python -c "import redis, rq; print('依赖安装成功')"

# 4. 给脚本添加执行权限
chmod +x scripts/start_web.sh scripts/start_worker.sh

# 5. 停止旧服务
systemctl --user stop tangdou-mp3 2>/dev/null || true

# 6. 安装 systemd 服务
cp scripts/tangdou-mp3.service ~/.config/systemd/user/
cp scripts/tangdou-worker.service ~/.config/systemd/user/
systemctl --user daemon-reload

# 7. 启动服务
systemctl --user start tangdou-mp3
systemctl --user start tangdou-worker

# 8. 设置开机自启
systemctl --user enable tangdou-mp3
systemctl --user enable tangdou-worker

# 9. 验证
systemctl --user status tangdou-mp3 --no-pager
curl http://localhost:18080/api/queue-stats
```

## 验证部署

```bash
# 查看服务状态
systemctl --user status tangdou-mp3
systemctl --user status tangdou-worker

# 查看队列状态
curl http://localhost:18080/api/queue-stats

# 查看日志
journalctl --user -u tangdou-mp3 -f
journalctl --user -u tangdou-worker -f
```

## 常见问题

### 1. uv 命令未找到

```bash
# 重新加载环境
source $HOME/.cargo/env

# 或添加到 .bashrc
echo 'source $HOME/.cargo/env' >> ~/.bashrc
```

### 2. 依赖安装失败

```bash
# 确保在虚拟环境中
cd /home/ryl/script/tangdou-web

# 使用 uv 安装
uv pip install redis rq

# 验证
.venv/bin/python -c "import redis, rq; print('OK')"
```

### 3. 服务启动失败

检查日志：
```bash
# Web 服务日志
journalctl --user -u tangdou-mp3 -n 50

# Worker 日志
journalctl --user -u tangdou-worker -n 50

# 手动测试启动脚本
./scripts/start_web.sh
./scripts/start_worker.sh
```

### 4. 端口被占用

```bash
# 查找占用 18080 的进程
sudo lsof -i :18080

# 或更换端口（编辑 scripts/start_web.sh）
```

## 回滚到单进程模式

如果 Redis 方案有问题，可以回滚：

```bash
# 1. 停止并禁用 Worker
systemctl --user stop tangdou-worker
systemctl --user disable tangdou-worker

# 2. 修改 Web 服务为单进程
# 编辑 scripts/start_web.sh，将 --workers 2 改为 --workers 1

# 3. 重启 Web 服务
systemctl --user restart tangdou-mp3
```

## 目录结构

```
/home/ryl/script/tangdou-web/
├── .venv/                      # uv 虚拟环境
│   ├── bin/
│   │   ├── python              # Python 解释器
│   │   └── gunicorn            # gunicorn (通过 pip 安装)
│   └── ...
├── scripts/
│   ├── start_web.sh            # Web 启动脚本
│   ├── start_worker.sh         # Worker 启动脚本
│   ├── tangdou-mp3.service     # Web systemd 配置
│   ├── tangdou-worker.service  # Worker systemd 配置
│   ├── deploy_check.sh         # 部署前检查
│   ├── deploy_redis_queue.sh   # 自动部署脚本
│   └── check_venv.sh           # 环境诊断
└── ...
```

## 更新依赖

```bash
cd /home/ryl/script/tangdou-web

# 使用 uv 更新
uv pip install -U redis rq

# 或重新安装 requirements
uv pip install -r requirements.txt

# 重启服务使更新生效
systemctl --user restart tangdou-mp3
systemctl --user restart tangdou-worker
```
