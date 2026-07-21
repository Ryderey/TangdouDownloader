FFmpeg 放置说明
================

本项目需要 FFmpeg 进行视频转音频处理。

Windows 7 用户：
1. 下载 FFmpeg Windows 版本（推荐 gyan.dev 或 BtbN 构建）：
   - https://www.gyan.dev/ffmpeg/builds/
   - https://github.com/BtbN/FFmpeg-Builds/releases

2. 选择 "ffmpeg-release-essentials.zip" 或类似版本

3. 解压后将以下两个文件复制到本目录 (bin/)：
   - ffmpeg.exe
   - ffprobe.exe

4. 最终目录结构：
   bin/
   ├── ffmpeg.exe
   ├── ffprobe.exe
   └── README.txt

注意：
- 如果 FFmpeg 已加入系统 PATH，则无需放入此目录
- 程序会优先查找 bin/ 目录，找不到再查 PATH
- .exe 文件不会被 Git 跟踪（已在 .gitignore 中排除）
