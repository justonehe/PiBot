# 🏗️ 架构设计：双树莓派分布式智能体系统

## 1. 核心理念

**"轻量化、解耦、各司其职"**
不依赖庞大的第三方 Agent 框架 (如 OpenClaw)，而是基于原生 Python + LLM API 构建一套可控、可扩展的 Master-Worker 系统。

---

## 2. 拓扑结构

```mermaid
graph TD
    User((用户)) <-->|视觉/触控| Master[Master 节点 (UI)]
    Cloud(火山引擎 LLM) <-->|API 调用| Master

    subgraph Master_Node [Master: pibot (192.168.10.113)]
        UI[Tkinter 界面]
        Router[意图识别/路由]
    end

    subgraph Worker_Node [Worker: pibot-brain (192.168.10.66)]
        Server[HTTP/MQTT 监听]
        Executor[执行器 (Shell/Docker)]
        Tools[技能库 (爬虫/下载/控制)]
    end

    Master --"指令 (JSON/HTTP)"--> Worker
    Worker --"执行结果"--> Master
```

---

## 3. 角色定义

### 🧠 Master Agent (交互中枢)

- **定位**: NanoBot (轻量级管家)。
- **硬件**: 接屏幕、麦克风、摄像头。
- **职责**:
  1.  **交互**: 接收用户输入 (文字/语音/图像)。
  2.  **思考**: 调用火山引擎 LLM，进行意图识别。
  3.  **决策**:
      - 如果是聊天/问答 -> 直接回复显示。
      - 如果是复杂任务 (如"帮我下载这个视频") -> **派发给 Worker**。
  4.  **反馈**: 将 Worker 的执行结果渲染给用户。

### 🤖 Worker Agent (执行中枢)

- **定位**: Silent Executor (静默执行者)。
- **硬件**: 无头模式 (Headless)，高性能 SD 卡或 SSD。
- **职责**:
  1.  **监听**: 随时等待 Master 的召唤。
  2.  **执行**: 运行耗时任务 (下载、编译、数据分析)。
  3.  **能力**: 集成各种 Tools (Shell, Python Scripts, APIs)。
  4.  **环境**: 可以在 Docker 中运行，保持环境隔离。

---

## 4. 通信协议 (API 设计)

建议初期使用 **HTTP REST API** (简单可靠)，后期可升级为 MQTT。

**Master -> Worker (POST /api/task)**

```json
{
  "task_id": "uuid-1234",
  "type": "shell",
  "content": "ping baidu.com -c 4",
  "timeout": 30
}
```

**Worker -> Master (Response)**

```json
{
  "status": "success",
  "output": "PING baidu.com ...",
  "duration": 4.2
}
```

---

## 5. 部署方案

- **Master**:
  - OS: Raspberry Pi OS Desktop
  - Software: Python 3, Tkinter, `openai` (SDK), `requests`.
- **Worker**:
  - OS: Raspberry Pi OS Lite
  - Software: Python 3, Flask (Web Server), `subprocess`.

## 6. 优势

1.  **响应快**: UI 不会因为后台跑死循环而卡顿。
2.  **更稳定**: Worker 挂了，Master 还能报错提示，不会黑屏。
3.  **可扩展**: 未来可以加更多 Worker。
