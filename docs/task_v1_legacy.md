# 任务清单

## ✅ 已完成

### Kindle 标注自动导入 Obsidian

- [x] 定位 `My Clippings.txt` 源文件
- [x] 编写 Python 解析脚本，实现去重和 Markdown 格式化
- [x] 执行全量导入，验证生成效果

### 🏫 教案 Dataview 仪表盘

- [x] 定位学期教案文件夹
- [x] 分析教案文件结构
- [x] 创建 `02_教学工作/教学仪表盘.md`
- [x] 整合到个人看板中心
- [x] 用户手动执行软链接命令激活 Dataview 索引

### 🏷️ Obsidian 标签体系重构 (Side Project 3)

- [x] **现状分析**
  - [x] 扫描全库所有标签（YAML + 正文 #标签）
  - [x] 统计标签频率，识别冗余/不规范 (`1e1e1e`, `include` 等噪音)
- [x] **规范设计**
  - [x] 查明异常标签来源 (`1e1e1e` 为误报)
  - [x] 确认重构策略 (用户 Review 实施计划)
  - [x] 设计新的标签层级体系 (健康->健康/运动, 学生->工作/学生管理)
- [x] **执行清洗**
  - [x] 运行清洗脚本 `refactor_tags.py` (修改了 192 个文件)
- [x] **可视化索引**
  - [x] 重写 `🏷️ 标签索引.md` 为 DataviewJS 动态视图
  - [x] 验证新标签的聚合效果

## 🚀 具身智能 (Project 4, 5 & 6)

### 🍓 具身智能 (Pibot 基础配置)

- [x] **连通性测试**
  - [x] 验证网络连接 (Ping/SSH) <!-- id: 30 -->
- [x] **基础环境配置**
  - [x] 系统更新 & 必要依赖安装 (Python, Git) <!-- id: 31 -->
- [x] **部署 MVP**
  - [x] 部署 Flow Console 脚本 (MVP) <!-- id: 32 -->

### 🌦️ 具身智能 (天气看板 v3.0)

- [x] **环境准备**
  - [x] 安装 GUI 库 (Tkinter) <!-- id: 40 -->
- [x] **代码实现**
  - [x] 编写全屏天气显示脚本 (wttr.in + Tkinter) <!-- id: 41 -->
  - [x] 远程部署与测试 <!-- id: 42 -->
- [x] **功能升级 (v2.0)**
  - [x] 接入和风天气 API (支持自定义 Host) <!-- id: 43 -->
  - [x] 集成待办事项显示 (Obsidian 同步脚本) <!-- id: 44 -->
- [x] **自动化部署 (v3.0)**
  - [x] 增加 3 天预报 <!-- id: 50 -->
  - [x] 配置 GUI 自动启动 (.desktop) <!-- id: 51 -->

### 👁️ 具身智能 (视觉 AI)

- [x] **硬件验证**
  - [x] 验证 USB 摄像头 (fswebcam/v4l2) <!-- id: 60 -->
  - [x] 验证 Google Coral TPU (lsusb) <!-- id: 61 -->
- [x] **硬件验证**
  - [x] 验证 USB 摄像头 (fswebcam/v4l2) <!-- id: 60 -->
  - [x] 验证 Google Coral TPU (lsusb) <!-- id: 61 -->
- [x] **环境搭建**
  - [x] 安装 PyCoral (失败) -> 转用 OpenCV + Tkinter GUI (Plan D) <!-- id: 62 -->
- [x] **应用开发**
  - [x] 部署动态捕捉 Demo (无需模型) <!-- id: 63 -->

### 🌐 网络基建 (Clash)

- [x] **核心部署**
  - [x] 下载 Clash Meta (Mihomo) 内核 <!-- id: 70 -->
  - [x] 配置 Systemd 守护进程 <!-- id: 71 -->
- [x] **配置管理**
  - [x] 导入订阅配置 (config.yaml) <!-- id: 72 -->
  - [x] 部署服务与 API (9090 端口) <!-- id: 73 -->
