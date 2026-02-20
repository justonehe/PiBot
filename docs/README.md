# PiBot V3 技术文档

## 版本历史

### v3.0.1 - 2026-02-20 (当前版本)
**安全修复和架构优化**

- ✅ 修复语法错误（f-string、重复定义）
- ✅ 移除硬编码 API 密钥
- ✅ 添加 Worker 忙时保护（HTTP 409）
- ✅ 添加配置占位符验证
- ✅ 添加回归测试套件
- ✅ 前端界面改进（时间戳、发信人标签）

**架构改进：**
- 统一 Master 数据源（移除重复函数）
- Worker 单任务串行执行
- 全局工具注册表并发安全

### v3.0.0 - 2026-02-19
**重大更新：Master-Worker 架构实现**

- ✅ 实现 Agent Core 核心模块（基于 pi-mono 架构）
- ✅ 部署 Worker 到 <WORKER_IP>
- ✅ 配置模型为 ark-code-latest
- ✅ Master 与 Worker 通信协议实现
- ✅ Systemd 服务自动启动配置
- ✅ 文档整合

**架构变更：**
- 从单节点架构升级为 Master-Worker 分布式架构
- 引入 TaskPlanner 任务复杂度分析
- 引入 WorkerPool 工作池管理
- 实现 HTTP REST API 通信协议

---

## 当前架构 (v3.0.0)

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         MASTER NODE                              │
│                      <MASTER_IP>:5000                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│   │  TaskPlanner │───▶│  WorkerPool  │───▶│  Worker (HTTP)  │  │
│   │  任务分析     │    │  Worker管理   │    │  <WORKER_IP>    │  │
│   └──────────────┘    └──────────────┘    └─────────────────┘  │
│          │                                                    │
│          ▼                                                    │
│   ┌──────────────┐                                           │
│   │  Agent Core  │  ◀── 简单任务本地处理                      │
│   │  本地执行    │                                           │
│   └──────────────┘                                           │
│          │                                                    │
│          ▼                                                    │
│   ┌──────────────┐                                           │
│   │  LLM Client  │  ◀── ark-code-latest                      │
│   │  Volcengine  │      https://ark.cn-beijing.volces.com    │
│   └──────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         WORKER NODE                              │
│                      <WORKER_IP>:5000                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   HTTP API Endpoints:                                           │
│   POST /task              - 接收任务                            │
│   GET  /task/:id/result   - 获取结果                            │
│   POST /task/:id/cancel   - 取消任务                            │
│   GET  /health            - 健康检查                            │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│   │  任务接收    │───▶│  Agent Core  │───▶│  技能执行    │    │
│   │  (Flask)     │    │  (临时实例)   │    │  (动态加载)   │    │
│   └──────────────┘    └──────────────┘    └──────────────┘    │
│                              │                                   │
│                              ▼                                   │
│                       ┌──────────────┐                          │
│                       │  内存清理    │  ◀── 任务完成后销毁     │
│                       └──────────────┘                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
PiBot/
├── master_hub.py              # Master 主程序（Flask + Agent Core）
├── agent_core.py              # Agent 核心循环
├── llm_client.py             # LLM 客户端（OpenAI 兼容）
├── tool_registry.py          # 工具注册表
├── master_components.py      # TaskPlanner + WorkerPool
├── worker_task_executor.py   # Worker HTTP 服务
├── skill_manager.py          # 技能加载与管理
├── dashboard.py              # Web 仪表盘（7寸屏幕优化）
│
├── skills/                   # 技能目录
│   ├── core.py               # 核心技能（shell、file、web）
│   ├── task_manager.py       # 任务管理技能
│   └── ...
│
├── tests/                    # 测试套件
│   └── test_regression_suite.py  # 回归测试
│
├── docs/                     # 文档
│   ├── README.md            # 详细文档（中文）
│   └── archive/             # 历史文档
│
├── services/                 # Systemd 服务文件
│   ├── pibot-hub.service    # Master 服务
│   └── pibot-kiosk.service  # Kiosk 显示服务
│
├── deploy_master.sh         # Master 部署脚本
├── deploy_worker.sh         # Worker 部署脚本
├── soul.md                  # Master 系统提示词
└── README.md                # 项目说明
```

---

### 核心组件

### 1. Agent Core (`agent_core.py`)
基于 pi-mono 架构实现的 Agent 运行时核心。

```python
class AgentCore:
    """Agent 运行时核心"""
    
    async def run(self, prompts, stream):
        # 1. 流式 LLM 响应
        # 2. 工具调用执行
        # 3. 事件流输出
        # 4. 消息生命周期管理
```

**特性：**
- 流式 LLM 响应
- Tool 执行与验证
- 事件流 (AgentEventStream)
- 支持 steering（用户中断）
- 最大迭代次数限制

#### 2. AI 加速层 (Hardware)
- **Google Coral Edge TPU**:
  - 驱动: `libedgetpu1-std`, `gasket-dkms`
  - 访问组: `apex`
  - 状态: 硬件已挂载 (USB 3.0), 待机 ID `1a6e:089a`
  - 建议: 使用 Docker (Python 3.9) 避开宿主机 Python 3.13 兼容性问题

#### 3. 网络基础设施 (Network)
- **中转代理 (NAS)**:
  - 节点: <PROXY_IP>:7890 (HTTP/HTTPS)
  - 类型: Mihomo (Clash Meta)
  - 功能: 自动分流, DNS 优化, 局域网共享

#### 2. LLM Client (`llm_client.py`)
OpenAI 兼容的 LLM 客户端。

```python
class LLMClient:
    """支持多提供商的 LLM 客户端"""
    
    # 支持的提供商
    - Volcengine (默认)
    - OpenAI
    - DeepSeek
    
    # 特性
    - 自动重试（指数退避）
    - HTTP 回退
    - 标准化响应格式
```

#### 3. Tool Registry (`tool_registry.py`)
工具注册与管理。

```python
class ToolRegistry:
    """工具注册表"""
    
    # 内置工具
    - file_read      # 文件读取
    - file_write     # 文件写入
    - shell_exec     # 命令执行
    - memory_read    # 记忆读取
    
    # 技能加载
    - 动态加载 Python 技能文件
    - JSON Schema 验证
```

#### 4. Master Components (`master_components.py`)
Master 专属组件。

```python
class TaskPlanner:
    """任务规划器"""
    
    async def analyze_task(task_description) -> TaskPlan:
        # 任务复杂度分析
        # SIMPLE   -> 本地处理
        # MODERATE -> 根据负载决定
        # COMPLEX  -> 分派给 Worker

class WorkerPool:
    """Worker 工作池"""
    
    - Worker 健康监控
    - 任务分派与结果收集
    - 并行执行支持
    - 超时与取消处理
```

#### 5. Worker Executor (`worker_task_executor.py`)
Worker HTTP 服务。

```python
class WorkerExecutor:
    """Worker 任务执行器"""
    
    # 特性
    - Flask HTTP API
    - 每任务独立 Agent Core 实例
    - 任务完成后内存清理
    - 支持技能动态加载
```

---

## 任务分派规则

| 任务类型 | 处理器 | 决策依据 |
|---------|--------|----------|
| 文件操作 | Master | Worker 无法访问 Master 文件系统 |
| 简单查询 | Master | 低延迟，无需分派 |
| 系统状态 | Master | 直接系统访问 |
| 网络/下载 | Worker | Worker 有独立网络连接 |
| 硬件/GPIO | Worker | Worker 有物理传感器 |
| 计算密集型 | Worker | 负载均衡 |
| 代码编写 | 两者 | 根据当前负载决定 |

---

## 通信协议

### Master → Worker (任务分派)

```http
POST http://<WORKER_IP>:5000/task
Content-Type: application/json

{
  "task_id": "task_001",
  "description": "下载天气数据",
  "skills": ["web_fetch", "file_ops"]
}
```

**响应：**
```json
{
  "success": true,
  "task_id": "task_001",
  "status": "accepted"
}
```

### Master → Worker (获取结果)

```http
GET http://<WORKER_IP>:5000/task/task_001/result
```

**响应：**
```json
{
  "task_id": "task_001",
  "description": "下载天气数据",
  "status": "completed",
  "result": {
    "output": "天气数据...",
    "data": {...}
  }
}
```

---

## 测试

```bash
# 运行回归测试
pytest -q

# 测试特定组件
pytest tests/test_regression_suite.py -v
```

---

## 路线图 / 下一步计划

### 架构改进
- [ ] **前后端分离** - 将 HTML/CSS/JS 从 `master_hub.py` 提取到独立的 `static/` 目录
  - 将 `HTML_BASE` 模板移至 `static/index.html`
  - 分离 CSS 到 `static/css/style.css`
  - 分离 JavaScript 到 `static/js/app.js`
  - 优势：更好的可维护性、现代开发工作流、关注点分离

### 功能特性
- [ ] WebSocket 支持，实现实时聊天流
- [ ] 任务队列持久化（Redis/SQLite）
- [ ] Dashboard 访问认证系统
- [ ] Coral TPU 集成，支持本地推理

---

## 配置文件

### Master (<MASTER_IP>)
**文件：** `~/pibot.env`

```bash
# LLM 配置
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=ark-code-latest

# Worker 配置
WORKER_1_IP=<WORKER_IP>
```

### Worker (<WORKER_IP>)
**文件：** `~/pibot-worker/.env`

```bash
# LLM 配置
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=ark-code-latest

# Worker 标识
WORKER_ID=worker-1
```

---

## 快速部署（开发环境）

开发过程中快速部署，在本地创建 `.deploy-config`（不提交到 git）：

```bash
# .deploy-config - 本地部署配置
SSH_USER=your_username
MASTER_IP=192.168.x.x
WORKER_IP=192.168.x.x

# 使用 rsync 快速部署：
rsync -avz --delete *.py skills/ $SSH_USER@$MASTER_IP:~/pibot-master/
rsync -avz --delete worker_task_executor.py skills/ $SSH_USER@$WORKER_IP:~/pibot-worker/
```

---

## 部署状态

### 当前部署

| 组件 | IP | 状态 | 备注 |
|------|-----|------|------|
| Master | <MASTER_IP> | ✅ 运行中 | PID: 2821 |
| Worker-1 | <WORKER_IP> | ✅ 运行中 | Systemd 服务 |

### 服务管理

**Worker 服务：**
```bash
# 查看状态
sudo systemctl status pibot-worker

# 查看日志
sudo journalctl -u pibot-worker -f

# 重启
sudo systemctl restart pibot-worker
```

**Master 进程：**
```bash
# 查看进程
ps aux | grep master_hub

# 查看日志
tail -f ~/logs/master.log

# 重启
pkill -f master_hub.py
source ~/pibot.env
python3 ~/master_hub.py
```

---

## 访问地址

- **Master Web**: http://<MASTER_IP>:5000
- **Dashboard**: http://<MASTER_IP>:5000/dashboard
- **Worker Health**: http://<WORKER_IP>:5000/health

---

## 技术栈

- **后端**: Python 3.11+, Flask, aiohttp
- **LLM**: Volcengine ark-code-latest
- **API**: OpenAI 兼容接口
- **通信**: HTTP REST API
- **进程管理**: Systemd
- **部署**: SSH + SCP

---

## 文档历史

- **v3.0.1** (2026-02-20): 同步英文版 README，添加路线图
- **v3.0.0** (2026-02-19): 整合所有文档，添加版本历史
- **v2.x** (2026-02-18): 修复阶段文档
- **v1.x** (早期): 初始架构文档

---

**当前版本: v3.0.1**  
**最后更新: 2026-02-20**  
**状态: 生产就绪** ✅
