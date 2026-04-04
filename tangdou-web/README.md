# 🎵 糖豆MP3提取器

糖豆广场舞视频自动下载、去广告、转MP3的Web工具。

## ✨ 功能特点

- 📱 **手机友好界面** - 简洁直观的操作体验
- 🚀 **一键提取** - 粘贴链接，自动处理
- ⏱️ **自动去广告** - 默认剪掉前5秒片头
- 💾 **省流量** - 自动选择最低清晰度下载
- 🔒 **内网穿透** - 通过Tailscale安全访问

## 🛠️ 技术栈

- **后端**: Flask + Gunicorn
- **包管理**: [uv](https://github.com/astral-sh/uv) (比 pip 快 10-100 倍)
- **视频处理**: FFmpeg (下载 → 剪辑 → 转MP3)
- **部署**: Ubuntu + Nginx + Tailscale

## 📁 项目结构

```
tangdou-web/
├── app.py                  # Flask主应用
├── wsgi.py                 # WSGI入口
├── requirements.txt        # Python依赖
├── README.md               # 项目文档
├── modules/                # 核心模块
│   ├── tangdou.py          # 视频API（复用原有代码）
│   ├── headers.py          # 请求头（复用原有代码）
│   └── downloader.py       # 下载处理（FFmpeg优化）
├── tasks/                  # 后台任务
│   └── processor.py        # 任务队列处理
├── templates/              # HTML模板
│   ├── base.html
│   └── index.html
├── static/downloads/       # 下载文件存储
└── scripts/                # 部署脚本
    ├── install.sh          # Ubuntu系统服务安装脚本
    ├── simple-run.sh       # 简单运行脚本（无需root）
    ├── start-dev.sh        # 开发启动脚本
    ├── deploy.sh           # 快速部署脚本
    └── uninstall.sh        # 清理卸载脚本
```

## 🚀 部署方式

### 方式一：简单运行（推荐个人使用）

适合临时使用或测试，无需 root 权限，不安装系统服务。

```bash
# 1. 将代码放到任意目录，例如 /opt
git clone <你的仓库地址> /opt/tangdou-web
cd /opt/tangdou-web

# 2. 运行简单启动脚本
sudo bash scripts/simple-run.sh

# 或手动启动
cd /opt/tangdou-web
uv venv
source .venv/bin/activate
uv pip install flask gunicorn requests beautifulsoup4 lxml
python app.py
```

访问地址：**http://<服务器IP>:5000**

### 方式二：系统服务安装（推荐长期运行）

适合服务器长期运行，开机自启，后台守护。

```bash
# 1. 上传代码到服务器
git clone <你的仓库地址> /home/user/tangdou-web
cd /home/user/tangdou-web

# 2. 运行安装脚本（会自动复制代码到 /opt/tangdou-mp3）
sudo bash scripts/install.sh

# 3. 启动 Tailscale
sudo tailscale up

# 4. 启动服务
sudo systemctl daemon-reload
sudo systemctl enable tangdou-mp3
sudo systemctl start tangdou-mp3
```

访问地址：**http://<Tailscale-IP>:18080**

> 注意：使用非标准端口 `18080` 避免与系统其他服务冲突

---

## 🔧 开发调试

```bash
cd tangdou-web

# 创建虚拟环境（使用 uv）
uv venv
source .venv/bin/activate

# 安装依赖
uv pip install flask gunicorn requests beautifulsoup4 lxml

# 检查 FFmpeg
ffmpeg -version

# 启动开发服务器
python app.py
```

访问 http://localhost:5000

---

## 📊 管理命令

### 系统服务方式

```bash
# 查看服务状态
sudo systemctl status tangdou-mp3

# 查看日志
sudo journalctl -u tangdou-mp3 -f

# 重启服务
sudo systemctl restart tangdou-mp3

# 停止服务
sudo systemctl stop tangdou-mp3
```

### 简单运行方式

```bash
# 直接 Ctrl+C 停止
# 或使用 pkill
pkill -f "python app.py"
```

---

## 🧹 清理环境

```bash
# 使用卸载脚本（删除系统服务和文件）
cd /path/to/tangdou-web
sudo bash scripts/uninstall.sh

# 或手动清理
sudo systemctl stop tangdou-mp3
sudo systemctl disable tangdou-mp3
sudo rm -f /etc/systemd/system/tangdou-mp3.service
sudo rm -f /etc/nginx/sites-available/tangdou-mp3
sudo rm -rf /opt/tangdou-mp3
sudo systemctl restart nginx
```

---

## 🔒 端口说明

| 用途 | 端口 | 说明 |
|------|------|------|
| HTTP 外部端口 | **18080** | Nginx 对外服务，避免 80 端口冲突 |
| 内部服务端口 | **15000** | Gunicorn 内部端口，避免常用端口 |
| 开发端口 | **5000** | Flask 开发服务器默认端口 |

如需修改端口：

```bash
# 系统服务方式 - 修改外部端口（Nginx）
sudo nano /etc/nginx/sites-available/tangdou-mp3

# 系统服务方式 - 修改内部端口（Gunicorn）
nano /opt/tangdou-mp3/gunicorn.conf.py

# 简单运行方式 - 修改端口
# 编辑 scripts/simple-run.sh 中的 PORT 变量
```

---

## 📝 使用说明

1. 打开糖豆APP，找到喜欢的广场舞视频
2. 点击分享，复制链接
3. 粘贴到网页输入框
4. 点击"开始提取"
5. 等待处理完成，下载MP3

![使用截图](README.assets/image-20260405001616384.png)

---

## ⚠️ 注意事项

1. **FFmpeg 必须安装** - 脚本会自动安装，如失败请手动安装
2. **磁盘空间** - 下载的视频会临时存储，定期自动清理
3. **Tailscale 网络** - 手机需要安装 Tailscale 并登录同一账号
4. **版权说明** - 请仅下载自己有权限使用的视频

---

## 📄 License

MIT License
