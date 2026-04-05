# 🎵 糖豆MP3提取器

糖豆广场舞视频自动下载、去广告、转MP3的Web工具。

## ✨ 功能简介

- 📱 **手机友好界面** - 简洁直观的操作体验
- 🚀 **一键提取** - 粘贴链接，自动处理
- ⏱️ **自动去广告** - 默认剪掉前5秒片头
- 💾 **省流量** - 自动选择最低清晰度下载
- 🔒 **内网穿透** - 通过Tailscale安全访问
- 📊 **任务队列** - 基于Redis的多进程任务处理

## 📁 目录结构

```
tangdou-web/
├── app.py                  # Flask主应用
├── wsgi.py                 # WSGI入口
├── requirements.txt        # Python依赖
├── start-single.sh         # 单worker启动脚本
├── modules/                # 核心模块
│   ├── tangdou.py          # 视频API（解析糖豆链接）
│   ├── headers.py          # HTTP请求头
│   └── downloader.py       # 视频下载器（FFmpeg处理）
├── tasks/                  # 后台任务
│   ├── processor.py        # Redis队列任务处理器
│   └── processor_memory.py # 内存模式处理器（降级）
├── templates/              # HTML模板
│   ├── base.html
│   └── index.html
├── static/downloads/       # 下载文件存储
└── scripts/                # 部署脚本
    ├── install.sh              # 系统级安装
    ├── install-user-service.sh # 用户级服务安装
    ├── start_web.sh            # Web服务启动
    ├── start_worker.sh         # Worker启动
    ├── deploy_check.sh         # 部署前检查
    ├── deploy_redis_queue.sh   # 自动部署
    └── tangdou-mp3.service     # systemd配置
```

## 🛠️ 环境依赖

### 系统依赖

- **Python** >= 3.8
- **FFmpeg** - 用于视频处理和格式转换
- **Redis** - 用于任务队列（生产环境）

### 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server

# 启动Redis
sudo systemctl enable redis-server --now
```

### Python依赖

```bash
# 使用pip
pip install -r requirements.txt

# 或使用uv（推荐）
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 依赖列表

| 包 | 版本 | 说明 |
|---|---|---|
| flask | >=2.3.0 | Web框架 |
| gunicorn | >=21.0.0 | WSGI服务器 |
| requests | >=2.31.0 | HTTP请求 |
| beautifulsoup4 | >=4.12.0 | HTML解析 |
| lxml | >=4.9.0 | XML/HTML解析器 |
| redis | >=5.0.0 | Redis客户端 |
| rq | >=1.15.0 | 任务队列 |

## 🚀 运行命令与使用方法

### 方式一：开发模式（单进程）

```bash
# 启动开发服务器
python app.py

# 访问 http://localhost:5000
```

### 方式二：简单运行（单worker，无Redis）

```bash
bash start-single.sh

# 访问 http://<服务器IP>:18080
```

### 方式三：生产部署（Redis + 多Worker）

```bash
# 1. 安装依赖并部署
cd /path/to/tangdou-web
bash scripts/deploy_redis_queue.sh

# 2. 启动服务
systemctl --user start tangdou-mp3      # Web服务
systemctl --user start tangdou-worker   # 任务处理器

# 3. 设置开机自启
systemctl --user enable tangdou-mp3
systemctl --user enable tangdou-worker
```

### 服务管理命令

```bash
# 查看状态
systemctl --user status tangdou-mp3
systemctl --user status tangdou-worker

# 启动/停止/重启
systemctl --user start tangdou-mp3
systemctl --user stop tangdou-mp3
systemctl --user restart tangdou-mp3

# 查看日志
journalctl --user -u tangdou-mp3 -f
journalctl --user -u tangdou-worker -f
```

### 使用步骤

1. 打开糖豆APP，找到喜欢的广场舞视频
2. 点击分享，复制链接
3. 在网页输入框粘贴链接
4. 设置需要跳过的片头时长（默认5秒）
5. 点击"开始提取"
6. 等待处理完成，下载MP3文件

## 🔄 核心流程说明

```
用户提交链接
    ↓
解析视频信息（VideoAPI）
    ↓
提交任务到Redis队列（TaskProcessor.submit）
    ↓
Worker获取任务执行（process_download_task）
    ↓
选择最低清晰度下载（VideoDownloader.download）
    ↓
FFmpeg剪辑并转MP3（clip_and_convert）
    ↓
清理临时视频文件
    ↓
标记任务完成，提供下载
```

### 处理流程详情

1. **链接解析** - 从糖豆分享链接中提取vid，调用API获取视频信息
2. **任务入队** - 生成任务ID，存入Redis队列等待处理
3. **视频下载** - Worker选择最低清晰度下载，节省流量
4. **剪辑转换** - FFmpeg从指定秒数开始剪辑，转换为MP3格式
5. **状态同步** - 进度实时更新到Redis，前端轮询获取状态
6. **文件清理** - 自动删除临时视频，MP3文件定期清理

## 📦 关键模块解释

### modules/tangdou.py

视频API模块，负责与糖豆服务器交互：

- `get_vid()` - 从URL中解析视频ID
- `VideoAPI` - 获取视频信息和下载地址
- `HTML` - 备用方案，通过HTML解析获取视频地址

### modules/downloader.py

视频下载处理器，核心功能实现：

- `VideoDownloader` - 主下载器类
- `select_lowest_quality()` - 智能选择最低清晰度
- `download()` - 流式下载视频
- `clip_and_convert()` - FFmpeg剪辑并转MP3
- `process_pipeline()` - 完整处理流程

### tasks/processor.py

任务队列处理器，基于Redis+RQ：

- `Task` - 任务数据模型
- `TaskStore` - Redis任务存储
- `process_download_task()` - Worker执行函数
- `TaskProcessor` - Web端任务管理器
- `get_processor()` - 全局处理器单例

### app.py

Flask主应用，提供HTTP接口：

| 接口 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 首页 |
| `/api/video-info` | POST | 获取视频预览信息 |
| `/api/submit` | POST | 提交处理任务 |
| `/api/status/<id>` | GET | 查询任务状态 |
| `/api/download/<file>` | GET | 下载MP3文件 |
| `/api/tasks` | GET | 获取最近任务列表 |
| `/api/cleanup` | POST | 手动清理旧文件 |
| `/api/storage-info` | GET | 存储使用情况 |
| `/api/queue-stats` | GET | 队列统计信息 |

## ⚠️ 注意事项

### 1. 必需依赖

- **FFmpeg必须安装** - 脚本会自动检查，如失败请手动安装
- **Redis生产环境必需** - 多worker模式需要Redis支持

### 2. 存储空间

- 下载的视频会临时存储在 `static/downloads/`
- MP3文件默认保留24小时后自动清理
- 可手动调用 `/api/cleanup` 接口立即清理

### 3. 网络访问

- 生产环境使用端口 **18080**
- 开发环境使用端口 **5000**
- 建议配合Tailscale实现内网穿透

### 4. 权限说明

- 用户级服务无需sudo，推荐个人/家庭使用
- 系统级服务需要sudo，适合多用户共享服务器

### 5. 版权提示

- 请仅下载自己有权限使用的视频
- 本项目仅供学习交流使用

### 6. 常见问题

**FFmpeg未安装**
```bash
sudo apt-get install ffmpeg
```

**Redis连接失败**
```bash
sudo systemctl start redis-server
```

**端口被占用**
```bash
# 查找占用进程
sudo lsof -i :18080
# 或修改启动脚本中的端口
```

**清理残留文件**
```bash
# 清理24小时前的文件
curl -X POST http://localhost:18080/api/cleanup

# 清理所有历史文件
curl -X POST http://localhost:18080/api/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_hours": 0}'
```

## 📄 License

MIT License
