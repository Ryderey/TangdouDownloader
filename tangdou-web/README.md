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
- **视频处理**: FFmpeg (下载 → 剪辑 → 转MP3)
- **部署**: Ubuntu + Nginx + Tailscale

## 📁 项目结构

```
tangdou-web/
├── app.py                  # Flask主应用
├── wsgi.py                 # WSGI入口
├── requirements.txt        # Python依赖
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
    ├── install.sh          # Ubuntu安装脚本
    ├── start-dev.sh        # 开发启动脚本
    └── deploy.sh           # 快速部署脚本
```

## 🚀 部署指南

### 1. 准备Ubuntu服务器

可以是云服务器、树莓派、旧电脑等，确保能联网。

### 2. 运行安装脚本

```bash
# 上传项目代码到服务器
scp -r ./tangdou-web user@your-server:/opt/

# SSH登录服务器
ssh user@your-server

# 运行安装脚本
cd /opt/tangdou-web
sudo bash scripts/install.sh
```

### 3. 启动Tailscale内网穿透

```bash
sudo tailscale up
```

记录分配的IP地址（如 `100.x.x.x`）或MagicDNS域名。

### 4. 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable tangdou-mp3
sudo systemctl start tangdou-mp3
sudo systemctl restart nginx
```

### 5. 访问使用

手机或其他设备连接同一个Tailscale网络后，访问：

```
http://100.x.x.x
```

## 📝 使用说明

1. 打开糖豆APP，找到喜欢的广场舞视频
2. 点击分享，复制链接
3. 粘贴到网页输入框
4. 点击"开始提取"
5. 等待处理完成，下载MP3

![image-20260405001616384](README.assets/image-20260405001616384.png)



## 🔧 开发调试

```bash
cd tangdou-web

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 检查FFmpeg
ffmpeg -version

# 启动开发服务器
python app.py
```

访问 http://localhost:5000

## 📊 管理命令

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

## ⚠️ 注意事项

1. **FFmpeg必须安装** - 脚本会自动安装，如失败请手动安装
2. **磁盘空间** - 下载的视频会临时存储，定期自动清理
3. **Tailscale网络** - 手机需要安装Tailscale并登录同一账号
4. **版权说明** - 请仅下载自己有权限使用的视频

## 📄 License

MIT License
