# 实施计划 - Project V3: 轻量级 Python 分布式 Agent

## 🚀 核心目标

放弃重量级框架，使用原生 Python 构建 **Double Agent** 系统。

- **Master (NanoBot)**: 负责 GUI 交互、LLM 对话、任务分发。
- **Worker (Executor)**: 负责接收指令、执行 Shell/Python 任务、返回结果。

## 🏗️ 架构设计

### 1. 技术栈

- **语言**: Python 3 (原生)。
- **LLM**: 火山引擎 API (兼容 OpenAI SDK)。
- **通信**: HTTP (Flask) 或 TCP Socket (简单直接)。
- **GUI**: Tkinter (Master 节点)。

### 2. 模块划分

#### Master Node (`pibot` / 113)

- `master_agent.py`:
  - 集成 `openai` 库调用火山引擎。
  - Tkinter 聊天界面 (Chatbox + Input)。
  - 工具路由：如果 LLM 返回 "Execute on Worker"，则转发给 Worker。

#### Worker Node (`pibot-brain` / 66)

- `worker_agent.py`:
  - Flask 服务 (Port 5000) 或 Socket Server。
  - API `/execute`: 接收 Shell 命令并执行。
  - API `/health`: 心跳检测。

## 📋 实施步骤

### Phase 1: 环境清理与准备

- [x] 终止 OpenClaw 安装。
- [ ] Master/Worker 安装 Python 依赖 (`openai`, `flask`, `requests`)。

### Phase 2: Worker 开发 (执行器)

- [ ] 编写 `worker_agent.py` (Flask Server)。
- [ ] 部署到 Worker 并启动。

### Phase 3: Master 开发 (大脑+交互)

- [ ] 编写 `master_agent.py` (Tkinter + LLM)。
- [ ] 配置火山引擎 API Key。
- [ ] 联调：Master 对话 -> 识别意图 -> 调用 Worker。

### Phase 4: 交付

- [ ] 设置 Systemd 自启。
- [ ] 演示：通过 Master 界面控制 Worker 下载文件或查询系统状态。
