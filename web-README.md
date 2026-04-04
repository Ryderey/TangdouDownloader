📁 项目结构
tangdou-web/
├── app.py                  # Flask主应用
├── wsgi.py                 # WSGI入口（生产部署）
├── requirements.txt        # Python依赖
├── README.md               # 项目文档
├── modules/                # 核心模块
│   ├── tangdou.py          # 复用：视频API
│   ├── headers.py          # 复用：请求头
│   ├── downloader.py       # 新建：FFmpeg下载处理
│   └── __init__.py
├── tasks/                  # 后台任务
│   ├── processor.py        # 新建：任务队列
│   └── __init__.py
├── templates/              # 前端模板
│   ├── base.html           # 基础布局
│   └── index.html          # 首页
├── static/downloads/       # MP3文件存储目录
└── scripts/                # 部署脚本
    ├── install.sh          # Ubuntu一键安装
    ├── start-dev.sh        # 开发启动
    └── deploy.sh           # 快速部署
🎯 核心功能实现
功能	实现方式
自动下载低清视频	选择 V360P/H360P 最低清晰度，节省流量
自动剪广告	FFmpeg -ss 5 跳过前5秒（可在高级选项调整）
转MP3	FFmpeg -vn -ar 44100 -b:a 192k 高效转换
后台任务队列	多线程处理，支持并发下载
自动清理	每小时自动删除24小时前的旧文件
🚀 部署步骤
# 1. 将代码上传到Ubuntu服务器
scp -r ./tangdou-web user@server:/opt/

# 2. SSH登录并运行安装脚本
ssh user@server
cd /opt/tangdou-web
sudo bash scripts/install.sh

# 3. 启动Tailscale
sudo tailscale up

# 4. 启动服务
sudo systemctl start tangdou-mp3
sudo systemctl restart nginx
📱 使用流程
用户粘贴链接 → 后台下载低清视频 → FFmpeg剪前5秒 → 转MP3 
     ↑                                                              ↓
  显示进度条                                                    提供下载按钮
🔧 关键优化点
默认行为: 用户什么都不用选，点击按钮直接得到MP3
省流量: 自动选择最低清晰度（因为只要音频）
去广告: 默认跳过前5秒（可调整）
高效处理: 直接用FFmpeg，比moviepy快10倍
手机友好: 响应式设计，操作简单
📋 文件说明
downloader.py - 核心处理逻辑，复用了原有的 tangdou.py API
processor.py - 后台任务队列，防止多人同时请求卡死
app.py - Flask API，提供提交/查询/下载接口
index.html - 简洁的单页应用，一键操作