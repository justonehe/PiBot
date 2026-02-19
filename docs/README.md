# PiBot V3 技术文档

## 版本历史

### v3.0.0 - 2026-02-19 (当前版本)
**重大更新：Master-Worker 架构实现**

- ✅ 实现 Agent Core 核心模块（基于 pi-mono 架构）
- ✅ 部署 Worker 到 192.168.10.66
- ✅ 配置模型为 ark-code-latest
- ✅ Master 与 Worker 通信协议实现
- ✅ Systemd 服务自动启动配置
- ✅ 文档整合

**架构变更：**
- 从单节点架构升级为 Master-Worker 分布式架构
- 引入 TaskPlanner 任务复杂度分析
- 引入 WorkerPool 工作池管理
- 实现 HTTP REST API 通信协议

### v2.x - 2026-02-18 (历史版本)
**修复和优化阶段**

- 修复 Dashboard 显示问题
- 修复 web_fetch skill 返回格式
- 优化内存管理（tape/memory）
- 添加 create_skill 模板
- 修复 systemd 服务配置

### v1.x - 早期版本
**初始架构**

- 基础 Master Hub 实现
- 简单 Skill 系统
- Flask Web 界面
- 本地文件队列通信

---

## 当前架构 (v3.0.0)

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         MASTER NODE                              │
│                      192.168.10.113:5000                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│   │  TaskPlanner │───▶│  WorkerPool  │───▶│  Worker (HTTP)  │  │
│   │  任务分析     │    │  Worker管理   │    │  192.168.10.66  │  │
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
│                      192.168.10.66:5000                          │
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

### 核心组件

#### 1. Agent Core (`agent_core.py`)
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
POST http://192.168.10.66:5000/task
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
GET http://192.168.10.66:5000/task/task_001/result
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

## 配置文件

### Master (192.168.10.113)
**文件：** `~/pibot.env`

```bash
# LLM 配置
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=ark-code-latest

# Worker 配置
WORKER_1_IP=192.168.10.66
```

### Worker (192.168.10.66)
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

## 部署状态

### 当前部署

| 组件 | IP | 状态 | 备注 |
|------|-----|------|------|
| Master | 192.168.10.113 | ✅ 运行中 | PID: 2821 |
| Worker-1 | 192.168.10.66 | ✅ 运行中 | Systemd 服务 |

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

- **Master Web**: http://192.168.10.113:5000
- **Dashboard**: http://192.168.10.113:5000/dashboard
- **Worker Health**: http://192.168.10.66:5000/health

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

- **v3.0.0** (2026-02-19): 整合所有文档，添加版本历史
- **v2.x** (2026-02-18): 修复阶段文档
- **v1.x** (早期): 初始架构文档

---

**当前版本: v3.0.0**  
**最后更新: 2026-02-19**  
**状态: 生产就绪** ✅
