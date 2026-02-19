# PiBot V3 新架构设计文档

## 1. 架构概述

### 1.1 角色定义

#### Master (系统管家)
- **核心职责**: 任务调度、Worker 管理、结果汇总
- **工作模式**: 始终保持运行，随时可响应用户
- **不亲自执行**: 除非是简单查询或必须由 Master 完成的任务

#### Worker (临时执行者)
- **核心职责**: 执行 Master 分配的子任务
- **工作模式**: 被动唤醒，任务完成即销毁
- **生命周期**: 任务开始 → 加载身份/技能 → 执行 → 返回结果 → 销毁记忆

### 1.2 工作流程

```
用户请求
   ↓
Master 评估任务复杂度
   ↓
┌─────────────────────┬─────────────────────┐
│ 简单任务            │ 复杂任务             │
│ (直接回答/查询)      │ (需要 Worker 执行)   │
├─────────────────────┼─────────────────────┤
│ Master 直接处理     │ 1. 拆分任务         │
│                     │ 2. 选择空闲 Worker  │
│                     │ 3. 分发子任务        │
│                     │ 4. 监控执行状态      │
│                     │ 5. 收集结果         │
│                     │ 6. 汇总汇报         │
└─────────────────────┴─────────────────────┘
```

## 2. Master 详细设计

### 2.1 System Prompt (Soul)

```markdown
你是 PiBot Master，一个家庭智能系统的管家。

## 核心职责
1. **任务评估**: 判断任务复杂度，决定自己处理还是分配给 Worker
2. **Worker 管理**: 监控 3 个 Worker 的状态（闲置/工作中/离线）
3. **任务拆分**: 将复杂任务拆分为可并行/串行的子任务
4. **结果评估**: 接收 Worker 结果，验证完整性，汇总汇报

## Worker 状态监控
你有 3 个 Worker:
- Worker-1: 通常处理 IO 密集型任务（文件、网络）
- Worker-2: 通常处理计算密集型任务（数据处理、分析）
- Worker-3: 备用/复杂任务协作

使用 <call_skill>get_worker_status</call_skill> 获取当前状态。

## 决策规则

### 简单任务（Master 直接处理）
- 问候、日常对话
- 简单的信息查询（天气、时间）
- 系统状态查看
- 不涉及文件/网络操作的问题

### 复杂任务（分配给 Worker）
- 文件操作（读/写/删除）
- 网络请求（爬取、下载）
- 长时间运行的任务
- 需要访问硬件的任务（GPIO、摄像头）
- 批量数据处理

## 任务拆分原则
1. **独立性**: 每个子任务尽可能独立，减少依赖
2. **粒度**: 拆分到"一个 Worker 可在 1-5 分钟内完成"
3. **并行**: 无依赖的任务并行分配给多个 Worker
4. **容错**: 考虑 Worker 失败，设计重试机制

## 结果处理
1. 接收 Worker 返回的结果
2. 验证结果是否完整/正确
3. 如有失败，决定是否重试或调整策略
4. 向用户汇报最终完成情况（简洁明了）

## 回复格式
- **分配任务**: "已将任务拆分为 X 部分，分配给 Worker-Y，预计 N 分钟完成"
- **进度更新**: "Worker-1 完成 [任务A]，Worker-2 执行中 [任务B]"
- **最终结果**: "任务完成。结果摘要：[关键信息]"

## 注意事项
- 始终保持可回复性，不要阻塞
- 任务执行期间，用户可随时询问进度
- 如所有 Worker 都忙，告知用户等待或建议稍后
```

### 2.2 核心组件

#### WorkerManager
```python
class WorkerManager:
    def __init__(self):
        self.workers = {
            "worker_1": Worker("worker_1", "<WORKER_IP>"),
            "worker_2": Worker("worker_2", "<WORKER_2_IP>"),  # 预留
            "worker_3": Worker("worker_3", "<WORKER_3_IP>"),  # 预留
        }
        self.task_queue = []  # 待分配任务
        self.active_tasks = {}  # 执行中任务
    
    def get_status(self) -> dict:
        """获取所有 Worker 状态"""
        pass
    
    def dispatch_task(self, task: dict) -> str:
        """分派任务给 Worker，返回任务 ID"""
        pass
    
    def collect_result(self, task_id: str) -> dict:
        """收集任务结果"""
        pass
```

#### TaskPlanner
```python
class TaskPlanner:
    def analyze(self, user_request: str) -> dict:
        """分析任务，返回执行计划"""
        # 使用 LLM 判断复杂度
        # 返回: {"type": "simple|complex", "subtasks": [...]}
        pass
    
    def split_task(self, task: str) -> list:
        """将复杂任务拆分为子任务"""
        pass
```

## 3. Worker 详细设计

### 3.1 生命周期

```
[休眠状态] ←──────────────────┐
    ↑                          │
    │ 收到任务                  │
    ↓                          │
[临时激活]                     │
    │                          │
    ├─ 1. 加载任务上下文       │
    ├─ 2. 激活技能             │
    ├─ 3. 执行任务             │
    ├─ 4. 生成结果             │
    ├─ 5. 返回结果给 Master    │
    │                          │
    ↓                          │
[销毁记忆] ────────────────────┘
```

### 3.2 临时身份定义

每个任务的 Worker 身份临时生成：

```python
# 任务开始时生成
task_identity = {
    "task_id": "task-20250219-001",
    "role": "Task Executor",
    "objective": "用户请求的具体目标",
    "context": "该任务的上下文信息",
    "skills": ["file_ops", "web_fetch", "shell"],  # 该任务需要的技能
    "constraints": ["安全限制", "资源限制"],
    "ttl": 300  # 最大执行时间（秒）
}
```

### 3.3 Worker System Prompt

```markdown
你是 PiBot Worker，一个临时任务执行者。

## 当前任务
任务 ID: {task_id}
任务目标: {objective}
任务上下文: {context}

## 可用技能
{skills_list}

## 约束
- 只能使用上述技能
- 必须在 {ttl} 秒内完成
- 如涉及危险操作（删除、覆盖），需二次确认
- 任务完成后必须返回结构化结果

## 执行流程
1. 理解任务目标
2. 规划执行步骤
3. 调用适当技能
4. 收集执行结果
5. 格式化输出
6. **返回结果后立即结束，删除所有本次任务的记忆**

## 返回格式
```json
{
    "task_id": "任务ID",
    "status": "success|failed|partial",
    "result": "执行结果摘要",
    "details": "详细信息（可选）",
    "artifacts": ["生成的文件路径", "截图等"],
    "duration": "执行耗时",
    "errors": ["错误信息（如有）"]
}
```

## 重要
- 你是临时存在的，只为完成这一个任务
- 不要记住之前的对话或任务
- 任务结束后，你的记忆会被清除
- 专注于当前任务，不要发散
```

### 3.4 Worker 实现

```python
# worker_executor.py
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path

class TaskWorker:
    """临时任务执行器"""
    
    def __init__(self, task_file: Path):
        self.task_file = task_file
        self.task_data = None
        self.task_id = None
        self.memory_dir = None  # 临时记忆目录
        
    def load_task(self):
        """加载任务定义"""
        with open(self.task_file, 'r') as f:
            self.task_data = json.load(f)
        self.task_id = self.task_data['task_id']
        # 创建临时工作目录
        self.memory_dir = Path(tempfile.mkdtemp(prefix=f"worker_{self.task_id}_"))
        
    def setup_environment(self):
        """设置临时环境"""
        # 加载技能
        # 设置临时记忆路径
        # 初始化 LLM 客户端
        pass
    
    def execute(self) -> dict:
        """执行任务"""
        start_time = time.time()
        try:
            # 1. 解析任务
            objective = self.task_data['objective']
            context = self.task_data.get('context', '')
            
            # 2. 规划执行
            plan = self.plan_execution(objective, context)
            
            # 3. 执行步骤
            results = []
            for step in plan['steps']:
                result = self.execute_step(step)
                results.append(result)
            
            # 4. 汇总结果
            final_result = {
                "task_id": self.task_id,
                "status": "success",
                "result": self.summarize_results(results),
                "details": results,
                "duration": int(time.time() - start_time)
            }
            
            return final_result
            
        except Exception as e:
            return {
                "task_id": self.task_id,
                "status": "failed",
                "result": str(e),
                "duration": int(time.time() - start_time)
            }
    
    def cleanup(self):
        """清理临时资源"""
        if self.memory_dir and self.memory_dir.exists():
            shutil.rmtree(self.memory_dir)
        # 删除任务文件
        self.task_file.unlink(missing_ok=True)
    
    def run(self):
        """完整生命周期"""
        try:
            self.load_task()
            self.setup_environment()
            result = self.execute()
            self.save_result(result)
        finally:
            self.cleanup()
```

## 4. 通信协议

### 4.1 Master → Worker

任务文件格式 (`task_{id}.json`):
```json
{
    "task_id": "task-20250219-001",
    "created_at": "2026-02-19T08:00:00Z",
    "objective": "抓取 https://example.com 并提取标题",
    "context": "用户想了解这个网站的内容",
    "priority": "normal",
    "ttl": 300,
    "skills_required": ["web_fetch", "file_write"],
    "master_callback": "http://<MASTER_IP>:5000/api/worker/result",
    "worker_id": "worker_1"
}
```

### 4.2 Worker → Master

结果文件格式 (`result_{id}.json`):
```json
{
    "task_id": "task-20250219-001",
    "worker_id": "worker_1",
    "status": "success",
    "result": "成功抓取网页，标题: Example Domain",
    "artifacts": ["/tmp/result_001.html"],
    "duration": 5,
    "completed_at": "2026-02-19T08:00:05Z"
}
```

## 5. 状态机

### Worker 状态
```
OFFLINE → IDLE → BUSY → IDLE → OFFLINE
   ↑                    ↓
   └──── 超时/错误 ─────┘
```

- **OFFLINE**: Worker 未启动
- **IDLE**: Worker 在线，等待任务
- **BUSY**: Worker 正在执行任务

### 任务状态
```
PENDING → DISPATCHED → RUNNING → COMPLETED
   │           │            │          │
   │           │            ↓          │
   │           │       FAILED ────────┤
   │           │            │          │
   │           └──── TIMEOUT ─────────┤
   │                                  │
   └──────────────────────────────────┘ (重试)
```

## 6. 实现步骤

1. **Phase 1**: 重构 Worker 为临时执行模式
2. **Phase 2**: 更新 Master 的 soul 和任务分配逻辑
3. **Phase 3**: 实现 Worker 状态监控
4. **Phase 4**: 实现任务拆分和结果汇总
5. **Phase 5**: 测试和优化

## 7. 示例场景

### 场景: "帮我整理下载文件夹"

**用户**: "整理我的下载文件夹，把图片移到 Pictures，文档移到 Documents"

**Master 思考**:
1. 这是一个文件操作任务，需要 Worker
2. 拆分为: 
   - 子任务1: 扫描下载文件夹，分类文件
   - 子任务2: 移动图片到 Pictures
   - 子任务3: 移动文档到 Documents
3. Worker-1 空闲，分配子任务1
4. 等待结果...

**Master 回复**: "已将任务拆分为 3 部分，正在分配给 Worker-1 执行，预计 2 分钟完成"

**Worker-1 执行**:
1. 激活临时身份
2. 执行文件扫描
3. 返回分类结果
4. 销毁记忆

**Master 接收结果**:
- 分析 Worker 返回的文件列表
- 分配移动任务给 Worker-2 和 Worker-3
- 监控执行

**Master 最终汇报**: 
"任务完成。扫描发现 15 个图片和 8 个文档，已全部移动到对应文件夹。移动过程中遇到 2 个重名文件，已自动重命名保存。"
