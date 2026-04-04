# 🐛 糖豆MP3提取器 - 问题排查指南

## ❓ "任务不存在" 问题排查

当你提交任务后，前端显示"任务不存在"，通常有以下几种原因：

---

## 1️⃣ 快速诊断

运行排查脚本：

```bash
cd ~/tangdou-web
bash scripts/debug.sh
```

---

## 2️⃣ 常见原因及解决方案

### 原因 A：应用重启导致任务丢失

**现象**：提交任务后，如果后端重启（代码修改、崩溃等），内存中的任务会丢失

**解决**：
- 重新提交任务
- 使用 `simple-run.sh` 或用户服务方式运行，避免频繁重启

---

### 原因 B：前后端端口不一致

**现象**：前端访问端口 A，但后端实际运行在端口 B

**检查**：
```bash
# 查看有哪些端口在运行
lsof -i :5000    # Flask 默认端口
lsof -i :18080   # 服务端口
```

**解决**：
- 确保访问地址正确，如 `http://IP:18080`
- 不要混用 `http://IP:5000` 和 `http://IP:18080`

---

### 原因 C：应用未正确运行

**检查应用状态**：

```bash
# 用户级服务
systemctl --user status tangdou-mp3

# 系统级服务
sudo systemctl status tangdou-mp3

# 查看进程
ps aux | grep -E "python|gunicorn"
```

**解决**：
```bash
# 重启服务
systemctl --user restart tangdou-mp3

# 或手动运行查看错误
cd ~/tangdou-web
source .venv/bin/activate
python app.py
```

---

### 原因 D：浏览器缓存或跨域问题

**排查**：
1. 按 `F12` 打开浏览器开发者工具
2. 切换到 **Console** 标签，查看红色错误
3. 切换到 **Network** 标签，找到 `submit` 请求
4. 查看响应状态码和返回内容

**常见错误**：
```
Failed to fetch    # 后端没运行或端口错误
CORS error         # 跨域问题
404 Not Found      # 接口不存在
500 Internal Error # 后端代码报错
```

---

## 3️⃣ 查看详细日志

### 方法 1：systemd 日志（推荐）

```bash
# 用户服务日志
journalctl --user -u tangdou-mp3 -f

# 系统服务日志
sudo journalctl -u tangdou-mp3 -f
```

### 方法 2：Flask 调试模式

```bash
cd ~/tangdou-web
source .venv/bin/activate
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

然后在浏览器重现问题，查看终端输出的详细错误。

### 方法 3：日志文件

```bash
# 查看日志文件
tail -f ~/tangdou-mp3/logs/error.log

# 或
tail -f ~/tangdou-web/logs/error.log
```

---

## 4️⃣ 手动测试 API

用 curl 测试后端是否正常：

```bash
# 1. 测试首页
curl http://localhost:18080/

# 2. 测试获取视频信息（会失败但应返回错误信息）
curl -X POST http://localhost:18080/api/video-info \
  -H "Content-Type: application/json" \
  -d '{"url":"test123"}'

# 3. 测试提交任务
curl -X POST http://localhost:18080/api/submit \
  -H "Content-Type: application/json" \
  -d '{"url":"test123","skip_time":"5"}'

# 4. 查看任务状态（用上面返回的 task_id）
curl http://localhost:18080/api/status/YOUR_TASK_ID
```

---

## 5️⃣ 完整重启流程

如果以上都无法解决，尝试完整重启：

```bash
# 1. 停止现有服务
systemctl --user stop tangdou-mp3 2>/dev/null || true
pkill -f "python.*app.py" 2>/dev/null || true
pkill -f "gunicorn" 2>/dev/null || true

# 2. 清理下载目录（可选）
rm -rf ~/tangdou-web/static/downloads/*

# 3. 重新安装依赖
cd ~/tangdou-web
source .venv/bin/activate
uv pip install flask gunicorn requests beautifulsoup4 lxml

# 4. 重新启动
# 方式 A：用户服务
bash scripts/install-user-service.sh

# 方式 B：手动调试
python app.py
```

---

## 6️⃣ 浏览器端排查

### 打开开发者工具

1. **Chrome/Edge**：按 `F12` 或 `Ctrl+Shift+I`
2. **Safari**：偏好设置 → 高级 → 勾选"在菜单栏中显示开发菜单"
3. **手机**：连接电脑，使用 Chrome 远程调试

### 关键查看点

**Console（控制台）标签**：
- 红色错误信息
- 网络请求失败提示

**Network（网络）标签**：
- 找到 `submit` 请求
- 查看 Status Code（200 表示成功）
- 查看 Response（返回内容）

**Application（应用）标签**：
- 查看 Local Storage 是否有缓存问题

---

## 7️⃣ 常见问题速查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 页面打不开 | 后端没运行/端口错误 | 检查服务状态，确认端口 |
| 点击无反应 | JavaScript 错误 | F12 查看 Console |
| 任务不存在 | 应用重启/任务过期 | 重新提交任务 |
| 进度卡住 | FFmpeg 出错 | 查看日志检查 FFmpeg |
| 下载失败 | 文件被删除/权限问题 | 检查 downloads 目录 |

---

## 8️⃣ 获取帮助

如果以上都无法解决，请提供以下信息：

1. **运行方式**：用户服务/系统服务/手动运行？
2. **访问地址**：完整 URL
3. **错误截图**：浏览器 F12 Console 和网络请求截图
4. **后端日志**：运行 `bash scripts/debug.sh` 选择 6 查看完整日志
