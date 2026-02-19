# PiBot V3 - Master-Worker Architecture Implementation

## Overview

The Master-Worker architecture has been fully implemented. This document describes the new components and how they work together.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           MASTER NODE                               │
│                      (192.168.10.113:5000)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │   TaskPlanner   │───▶│   WorkerPool     │───▶│ 3 Workers    │  │
│  │  (Analyzes      │    │ (Manages         │    │   HTTP API   │  │
│  │   task          │    │  Workers)        │    │              │  │
│  │   complexity)   │    └──────────────────┘    └──────┬───────┘  │
│  └─────────────────┘                                  │          │
│           │                                           │          │
│           ▼                                           ▼          │
│  ┌─────────────────┐                         ┌──────────────┐  │
│  │  Local Agent    │                         │   Worker 1   │  │
│  │    Core         │                         │192.168.10.66 │  │
│  │ (Simple tasks)  │                         └──────────────┘  │
│  └─────────────────┘                                  ▲          │
│           │                                           │          │
│           │                              ┌────────────┴───────┐  │
│           │                              │   Worker 2         │  │
│           │                              │192.168.10.67:5000  │  │
│           │                              └────────────┬───────┘  │
│           │                                           │          │
│           │                              ┌────────────┴───────┐  │
│           │                              │   Worker 3         │  │
│           │                              │192.168.10.68:5000  │  │
│           │                              └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         WORKER NODES                                │
│                    (3x Raspberry Pi Zeros)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              Worker Task Executor (Flask)                   │  │
│  │                  Port: 5000                                 │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │                                                             │  │
│  │  POST /task           → Receive task from Master           │  │
│  │  GET  /task/:id/result → Get task result                   │  │
│  │  POST /task/:id/cancel → Cancel task                       │  │
│  │  GET  /health         → Health check                       │  │
│  │  GET  /status         → Worker status                      │  │
│  │                                                             │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │              Agent Core (Per Task)                  │  │  │
│  │  ├─────────────────────────────────────────────────────┤  │  │
│  │  │ • Load specified skills                             │  │  │
│  │  │ • Execute task                                      │  │  │
│  │  │ • Return result                                     │  │  │
│  │  │ • DESTROY memory after completion                   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## New Components

### 1. **agent_core.py** - Core Agent Loop
- Implements the pi-mono agent-loop.ts pattern in Python
- Provides `AgentCore` class with streaming LLM responses
- Tool execution with validation
- Event streaming for UI updates
- Message lifecycle management

Key Classes:
- `AgentCore` - Main agent loop
- `AgentContext` - Conversation context
- `AgentTool` - Tool definition
- `ToolResult` - Tool execution result
- `AgentMessage` - Message types

### 2. **llm_client.py** - LLM Client Adapter
- OpenAI-compatible API client
- Supports multiple providers (Volcengine, OpenAI, DeepSeek)
- Automatic retry with exponential backoff
- Fallback to aiohttp if openai library not available

Key Classes:
- `LLMClient` - Generic client
- `VolcengineClient` - Volcengine-specific
- `AgentCoreWithLLM` - AgentCore with LLM integration

### 3. **tool_registry.py** - Tool Registry
- Manages tool registration and execution
- Loads skills from Python files
- Provides built-in tools (file_read, file_write, shell_exec, memory_read)
- Global registry singleton

Key Classes:
- `ToolRegistry` - Tool management
- Built-in tools for common operations

### 4. **master_components.py** - Master Components
- TaskPlanner: Analyzes task complexity and creates execution plans
- WorkerPool: Manages 3 workers, assigns tasks, monitors health

Key Classes:
- `TaskPlanner` - Task analysis and planning
- `WorkerPool` - Worker management
- `WorkerInfo` - Worker metadata
- `TaskPlan` - Execution plan
- `SubTask` - Subtask definition

### 5. **worker_task_executor.py** - Worker Task Executor
- Flask app for Worker nodes
- Receives tasks from Master
- Creates temporary Agent Core per task
- Destroys memory after task completion

Key Classes:
- `WorkerExecutor` - Main executor
- `Task` - Task representation
- Flask routes for HTTP API

## Task Assignment Rules

| Task Type | Handler | Reason |
|-----------|---------|--------|
| File operations | Master | Worker can't access Master's filesystem |
| Simple queries | Master | Low latency, no need to delegate |
| System status | Master | Direct system access |
| Network/download | Worker | Worker has independent internet connection |
| Hardware/sensors | Worker | Physical GPIO/sensor access |
| Compute-intensive | Worker | Distribute load |
| Code writing | Either | Decide based on current load |

## Communication Protocol

### Master → Worker (Task Assignment)
```http
POST http://192.168.10.66:5000/task
Content-Type: application/json

{
  "task_id": "task_001",
  "description": "Download weather data from API",
  "skills": ["web_fetch", "file_ops"]
}
```

Response:
```json
{
  "success": true,
  "task_id": "task_001",
  "status": "accepted"
}
```

### Master → Worker (Get Result)
```http
GET http://192.168.10.66:5000/task/task_001/result
```

Response:
```json
{
  "task_id": "task_001",
  "description": "Download weather data...",
  "status": "completed",
  "result": {
    "output": "Weather data: ...",
    "message_count": 5
  },
  "started_at": 1708368000,
  "completed_at": 1708368010
}
```

### Master → Worker (Health Check)
```http
GET http://192.168.10.66:5000/health
```

Response:
```json
{
  "status": "healthy",
  "worker_id": "worker-1",
  "current_task": null
}
```

## Worker Lifecycle

1. **Task Received**
   - Master POSTs task to Worker
   - Worker creates Task object
   - Worker responds with 202 Accepted

2. **Execution**
   - Worker loads specified skills
   - Creates fresh AgentCore instance
   - Executes task
   - Streams events (optional)

3. **Completion**
   - Task status updated to completed/failed
   - Result stored in Task object
   - Memory cleared (tools, context destroyed)
   - Worker becomes available

4. **Result Retrieval**
   - Master polls GET /task/:id/result
   - Returns current status and result

## Environment Variables

### Master Node
```bash
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=doubao-seed-code

# Worker IPs
WORKER_1_IP=192.168.10.66
WORKER_2_IP=192.168.10.67
WORKER_3_IP=192.168.10.68
```

### Worker Nodes
```bash
VOLC_API_KEY=your_api_key  # Same as Master
WORKER_ID=worker-1  # Unique identifier
```

## Usage Example

### Starting Workers

On each Worker Pi (192.168.10.66, 67, 68):
```bash
cd /path/to/pibot
python3 worker_task_executor.py --port 5000 --worker-id worker-1
```

### Using in Master

```python
from master_components import TaskPlanner, create_default_worker_pool
from llm_client import create_llm_client_from_env

# Initialize
llm_client = create_llm_client_from_env()
planner = TaskPlanner(llm_client)
worker_pool = create_default_worker_pool()

# Analyze task
plan = await planner.analyze_task("Download weather data")

if plan.handle_locally:
    # Execute locally
    result = await execute_local(plan)
else:
    # Delegate to worker
    subtask = plan.subtasks[0]
    result = await worker_pool.execute_task(subtask)
    
print(result)
```

## Files Created

1. `agent_core.py` - 550+ lines
2. `llm_client.py` - 350+ lines
3. `tool_registry.py` - 450+ lines
4. `master_components.py` - 600+ lines
5. `worker_task_executor.py` - 400+ lines

**Total: ~2,350 lines of new code**

## Next Steps

1. **Update soul.md** - Deploy new Master system prompt
2. **Integration testing** - Test Master-Worker communication
3. **Update master_hub.py** - Integrate new components into existing Master
4. **Deploy workers** - Install and run on Worker Pis
5. **Documentation** - Create deployment guide

## Benefits of New Architecture

1. **Scalability** - Distribute compute across 3 Workers
2. **Isolation** - Each task runs in fresh environment
3. **Specialization** - Workers can have different hardware/sensors
4. **Reliability** - If one Worker fails, others continue
5. **Performance** - Parallel execution of subtasks
6. **Clean Separation** - Master focuses on coordination

## Migration Notes

The new architecture is backward compatible:
- Existing skills work without modification
- Master can still operate in standalone mode
- Gradual migration: start with 1 Worker, add more later
