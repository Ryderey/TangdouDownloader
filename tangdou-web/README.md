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
    ├── install.sh              # 系统级安装（需要sudo）
    ├── install-user-service.sh # 用户级服务安装（推荐⭐）
    ├── simple-run.sh           # 简单运行（前台）
    ├── start-dev.sh            # 开发启动
    ├── deploy.sh               # 快速部署
    └── uninstall.sh            # 清理卸载
```

## 🚀 部署方式

### 方式一：用户级服务（推荐⭐）

**无需 sudo**，后台常驻运行，支持开机自启。

```bash
# 1. 下载代码到用户目录
cd ~
git clone <你的仓库地址> tangdou-web
cd tangdou-web

# 2. 安装用户服务（无需 sudo！）
bash scripts/install-user-service.sh

# 3. 按提示启动服务即可
```

### 管理命令（无需 sudo）：

```bash
# 启动/停止/重启
systemctl --user start tangdou-mp3
systemctl --user stop tangdou-mp3
systemctl --user restart tangdou-mp3

# 查看状态
systemctl --user status tangdou-mp3

# 查看日志
journalctl --user -u tangdou-mp3 -f

# 开机自启（已默认启用）
systemctl --user enable tangdou-mp3
```

**访问地址：** `http://<服务器IP>:18080`

> 💡 **提示**：用户服务默认在用户登出后停止。如需后台常驻（即使登出也运行）：
> ```bash
> sudo loginctl enable-linger $USER
> ```

---

### 方式二：系统级服务（需要 sudo）

适合多用户共享的服务器，需要 root 权限。

```bash
# 1. 下载代码
cd ~
git clone <你的仓库地址> tangdou-web
cd tangdou-web

# 2. 安装系统服务
sudo bash scripts/install.sh

# 3. 选择安装方式：
#    1) 系统目录 (/opt/tangdou-mp3) - 需要 sudo
#    2) 用户目录 ($HOME/tangdou-mp3) - 无需 sudo

# 4. 启动服务
sudo systemctl start tangdou-mp3
```

---

### 方式三：简单运行（前台运行）

适合临时测试，关闭终端即停止。

```bash
cd ~/tangdou-web
sudo bash scripts/simple-run.sh
```

或手动：
```bash
cd ~/tangdou-web
uv venv && source .venv/bin/activate
uv pip install flask gunicorn requests beautifulsoup4 lxml
python app.py
```

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

## 🧹 清理环境

### 用户级服务清理
```bash
# 停止并禁用服务
systemctl --user stop tangdou-mp3
systemctl --user disable tangdou-mp3

# 删除服务文件
rm ~/.config/systemd/user/tangdou-mp3.service

# 删除安装目录
rm -rf ~/tangdou-mp3

# 重载配置
systemctl --user daemon-reload
```

### 系统级服务清理
```bash
sudo bash scripts/uninstall.sh
```

---

### 清理下载残留文件

会自动定时删除残留文件，下面列举手动调接口删除残留：

```bash
# 手动清理（默认清理24小时前的文件）：
curl -X POST http://localhost:18080/api/cleanup \
  -H "Content-Type: application/json" \
  -d '{}'


# 清理所有历史文件：
curl -X POST http://localhost:18080/api/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_hours": 0}'
  
# 查看存储使用情况：
curl http://localhost:18080/api/storage-info

```



## 🔒 端口说明

| 用途 | 端口 | 说明 |
|------|------|------|
| 开发/简单模式 | **5000** | Flask 默认端口 |
| 用户/系统服务 | **18080** | Gunicorn 服务端口 |

---

## 📂 目录选择建议

| 场景 | 推荐目录 | 是否需要 sudo |
|------|---------|--------------|
| 个人使用 | `~/tangdou-web` 或 `~/tangdou-mp3` | ❌ 不需要 |
| 家庭服务器 | `~/tangdou-web` | ❌ 不需要 |
| VPS/云服务器 | `~/tangdou-web` | ❌ 不需要 |
| 多用户共享 | `/opt/tangdou-mp3` | ⚠️ 需要 |

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

1. **FFmpeg 必须安装** - 脚本会自动检查，如失败请手动安装
2. **磁盘空间** - 下载的视频会临时存储，定期自动清理
3. **Tailscale 网络** - 手机需要安装 Tailscale 并登录同一账号
4. **版权说明** - 请仅下载自己有权限使用的视频

---

## 📄 License

MIT License
