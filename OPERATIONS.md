# Tangdou Web 运维手册

本文档面向 `/home/ryl/script/tangdou-web` 的 Redis + RQ 部署。

## 关键路径与服务

- 项目目录：`/home/ryl/script/tangdou-web`
- Web 服务：`tangdou-mp3`
- Worker 服务：`tangdou-worker`
- 定时清理：`tangdou-cleanup.timer`，每 30 分钟执行一次
- Redis 队列：`rq:queue:tangdou`
- 任务状态：Redis `tangdou:task:*` + 本地 `static/downloads/.tasks/*.json`
- 去重键：Redis `tangdou:dedupe:*`
- 默认音频处理：前裁 5 秒、后裁 3 秒、重复拼接 x2
- 默认保留时间：3 小时，可用 `TANGDOU_RETENTION_HOURS` 覆盖

## 常用检查

```bash
cd /home/ryl/script/tangdou-web

systemctl --user status tangdou-mp3
systemctl --user status tangdou-worker
systemctl --user status tangdou-cleanup.timer

journalctl --user -u tangdou-mp3 -n 100 --no-pager
journalctl --user -u tangdou-worker -n 100 --no-pager
journalctl --user -u tangdou-cleanup.service -n 100 --no-pager

redis-cli ping
redis-cli llen rq:queue:tangdou
curl http://localhost:18080/api/queue-stats
```

如果在 root shell 中代管 `ryl` 的用户服务，需要带上用户 bus：

```bash
sudo -u ryl env XDG_RUNTIME_DIR=/run/user/1000 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  systemctl --user status tangdou-worker
```

## 自动清理策略

默认保留 3 小时内的任务状态、MP3 和临时文件。`scripts/cleanup.py` 会清理：

- 过期任务 JSON：`static/downloads/.tasks/*.json`
- 任务关联的 MP3 和临时视频
- 孤立的过期 `.mp3`、`.mp4`、`.part`
- 失效去重键

查看定时器：

```bash
systemctl --user list-timers tangdou-cleanup.timer
systemctl --user status tangdou-cleanup.timer
```

## 手动清理过时文件

只执行默认 3 小时清理：

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/cleanup.py
```

指定保留时间：

```bash
.venv/bin/python scripts/cleanup.py --max-age-hours 6
```

清理全部历史任务和生成文件：

```bash
.venv/bin/python scripts/cleanup.py --max-age-hours 0
```

只清理任务状态、临时视频和 `.part`，保留 MP3：

```bash
.venv/bin/python scripts/cleanup.py --max-age-hours 0 --keep-mp3
```

## 手动清理 Redis 缓存

优先使用脚本 `scripts/cleanup_redis.py`。该脚本默认只演练并打印将删除的 key；确认删除必须加 `--yes`。

查看可操作项：

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/cleanup_redis.py --help
```

只清理失效去重键：

```bash
.venv/bin/python scripts/cleanup_redis.py --stale-dedupe
.venv/bin/python scripts/cleanup_redis.py --stale-dedupe --yes
```

释放某个任务的去重占位，让同一视频和相同处理参数可以重新提交：

```bash
.venv/bin/python scripts/cleanup_redis.py --release-task 8588775f
.venv/bin/python scripts/cleanup_redis.py --release-task 8588775f --yes
```

清理 Redis 中的任务状态，但保留本地 JSON：

```bash
.venv/bin/python scripts/cleanup_redis.py --state
.venv/bin/python scripts/cleanup_redis.py --state --yes
```

清空 RQ 队列和相关 job。执行前先停 Worker，避免任务正在消费：

```bash
systemctl --user stop tangdou-worker
.venv/bin/python scripts/cleanup_redis.py --rq
.venv/bin/python scripts/cleanup_redis.py --rq --yes
systemctl --user start tangdou-worker
```

清理 Tangdou Redis 状态、去重键和 RQ 队列。该操作会丢弃 Redis 内待处理任务，执行前应停止 Web 和 Worker：

```bash
systemctl --user stop tangdou-mp3 tangdou-worker
.venv/bin/python scripts/cleanup_redis.py --all
.venv/bin/python scripts/cleanup_redis.py --all --yes
systemctl --user start tangdou-mp3 tangdou-worker
```

确需直接用 `redis-cli` 时，建议先扫描确认：

```bash
redis-cli --scan --pattern 'tangdou:*'
redis-cli --scan --pattern 'tangdou:dedupe:*'
```

批量删除示例：

```bash
redis-cli --scan --pattern 'tangdou:dedupe:*' | xargs -r redis-cli del
```

不要直接 `FLUSHDB`，除非该 Redis DB 只给本项目使用。

## 去重排查

重复提交返回 HTTP `409` 时，说明同一视频和相同处理参数在保留期内已有处理中或已完成任务。排查步骤：

```bash
curl http://localhost:18080/api/tasks
redis-cli --scan --pattern 'tangdou:dedupe:*'
```

如果确认需要重新提交，可以释放指定任务的去重键：

```bash
.venv/bin/python scripts/cleanup_redis.py --release-task <task_id> --yes
```

失败任务会自动释放去重键。已完成任务的去重键默认保留 3 小时。

## Redis 不可用时

Redis 不可用时，`/api/submit` 会返回 HTTP `503`，不会创建新任务。已有任务状态仍可从 `static/downloads/.tasks/*.json` 读取。

处理流程：

```bash
redis-cli ping
sudo systemctl status redis-server
sudo systemctl restart redis-server
systemctl --user restart tangdou-worker
curl http://localhost:18080/api/queue-stats
```

Worker 启动时会扫描本地未完成任务，并在 RQ 中缺少同名 job 时用原 `task_id` 重新入队。

## Worker 不消费队列

```bash
systemctl --user status tangdou-worker
journalctl --user -u tangdou-worker -n 100 --no-pager
redis-cli llen rq:queue:tangdou
curl http://localhost:18080/api/queue-stats
```

当前 Worker 必须通过项目脚本启动：

```bash
cd /home/ryl/script/tangdou-web
.venv/bin/python scripts/rq_worker.py
```

不要使用旧的 `python -m rq` 或带 `--job-ttl`、`--logging-level` 的 RQ CLI 启动方式。

## 部署或更新服务

```bash
cd /home/ryl/script/tangdou-web
./scripts/deploy_redis_queue.sh
```

脚本会安装 Redis/RQ 依赖、复制 Web/Worker/Cleanup systemd 用户服务并启用定时清理。
