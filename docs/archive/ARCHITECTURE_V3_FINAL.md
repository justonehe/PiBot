# PiBot V3 架构设计（参考 pi-mono 优化版）

## 从 pi-mono 学到的关键设计

### 1. 分层架构

```
┌─────────────────────────────────────────┐
│           PiBot Master                   │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │  Chat    │ │  Planner │ │ Monitor │ │
│  │  Interface│ │          │ │         │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       │            │            │       │
│       └────────────┼────────────┘       │
│                    ↓                     │
│            ┌──────────────┐              │
│            │  Agent Core  │              │
│            │  - Tool Call │              │
│            │  - State Mgmt│              │
│            └──────┬───────┘              │
│                   ↓                      │
│            ┌──────────────┐              │
│            │   LLM API    │              │
│            │ (统一接口)   │              │
│            └──────────────┘              │
└─────────────────────────────────────────┘
                    │
                    │ HTTP/SSH
                    ↓
┌─────────────────────────────────────────┐
│           PiBot Worker                   │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │  Task    │ │  Code    │ │  Tools  │ │
│  │  Executor│ │  Agent   │ │         │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       │            │            │       │
│       └────────────┼────────────┘       │
│                    ↓                     │
│            ┌──────────────┐              │
│            │  Agent Core  │              │
│            │  (临时激活)   │              │
│            └──────┬───────┘              │
│                   ↓                      │
│            ┌──────────────┐              │
│            │   LLM API    │              │
│            │ (同Master配置)│              │
│            └──────────────┘              │
└─────────────────────────────────────────┘
```

### 2. Agent Core 核心功能（参考 pi-mono/agent）

Agent Core 是 Master 和 Worker 共享的核心：

```python
class AgentCore:
    """Agent 运行时核心"""
    
    def __init__(self, config):
        self.llm = LLMClient(config.llm)  # 统一 LLM 接口
        self.tools = ToolRegistry()        # 工具注册表
        self.state = StateManager()        # 状态管理
        self.memory = MemoryManager()      # 记忆管理（临时）
    
    async def run(self, task: Task) -> Result:
        """运行任务"""
        # 1. 构建系统提示
        system_prompt = self.build_system_prompt(task)
        
        # 2. LLM 规划
        plan = await self.llm.plan(system_prompt, task.objective)
        
        # 3. 执行步骤
        for step in plan.steps:
            if step.type == "tool_call":
                result = await self.tools.execute(step.tool, step.args)
            elif step.type == "code":
                result = await self.execute_code(step.code)
            elif step.type == "llm":
                result = await self.llm.ask(step.prompt)
            
            # 更新状态
            self.state.update(step, result)
        
        # 4. 生成结果
        return self.generate_result()
```

### 3. 工具调用机制（Tool Calling）

统一的工具注册和调用：

```python
class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self.tools = {}
    
    def register(self, name: str, handler: Callable, schema: dict):
        """注册工具"""
        self.tools[name] = {
            "handler": handler,
            "schema": schema,  # JSON Schema 定义参数
            "description": schema["description"]
        }
    
    async def execute(self, name: str, args: dict) -> dict:
        """执行工具"""
        tool = self.tools.get(name)
        if not tool:
            raise ToolNotFound(name)
        
        # 验证参数
        validate(args, tool["schema"])
        
        # 执行
        result = await tool["handler"](**args)
        
        return {
            "tool": name,
            "args": args,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
```

### 4. Master 特殊组件

#### 4.1 Planner（任务规划器）

```python
class TaskPlanner:
    """任务规划器 - Master 特有"""
    
    async def analyze(self, user_request: str) -> TaskPlan:
        """分析任务并生成执行计划"""
        
        prompt = f"""
        分析用户请求，决定如何执行：
        
        用户请求: {user_request}
        
        决策：
        1. 这是简单任务还是复杂任务？
        2. 需要访问本地文件吗？
        3. 需要网络访问吗？
        4. 需要代码编写吗？
        
        返回 JSON:
        {{
            "complexity": "simple|complex",
            "executor": "master|worker",
            "reason": "为什么这样决策",
            "skills_required": ["skill1", "skill2"],
            "estimated_time": "1-5 minutes",
            "subtasks": [
                {{
                    "id": "task_1",
                    "objective": "具体目标",
                    "worker": "worker_1",
                    "skills": ["web_fetch", "code_writer"],
                    "dependencies": []
                }}
            ]
        }}
        """
        
        response = await self.llm.ask(prompt)
        return TaskPlan.parse(response)
```

#### 4.2 WorkerPool（Worker 管理器）

```python
class WorkerPool:
    """Worker 池管理"""
    
    def __init__(self):
        self.workers = {
            "worker_1": WorkerProxy("<WORKER_IP>", "file_io"),
            "worker_2": WorkerProxy("<WORKER_2_IP>", "network"),
            "worker_3": WorkerProxy("<WORKER_3_IP>", "compute")
        }
    
    async def get_status(self) -> dict:
        """获取所有 Worker 状态"""
        statuses = {}
        for wid, worker in self.workers.items():
            statuses[wid] = await worker.ping()
        return statuses
    
    async def dispatch(self, task: SubTask) -> TaskId:
        """分派任务给 Worker"""
        # 选择合适的 Worker
        worker = self.select_worker(task)
        
        # 序列化任务
        task_def = {
            "task_id": generate_id(),
            "objective": task.objective,
            "skills_required": task.skills,
            "context": task.context,
            "ttl": task.timeout,
            "created_at": datetime.now().isoformat()
        }
        
        # 发送到 Worker
        task_file = await worker.send_task(task_def)
        
        # 启动 Worker 执行器
        await worker.execute(task_file)
        
        return task_def["task_id"]
    
    def select_worker(self, task: SubTask) -> WorkerProxy:
        """选择最合适的 Worker"""
        # 根据任务类型和 Worker 负载选择
        candidates = [w for w in self.workers.values() if w.is_idle()]
        # 选择负载最低的
        return min(candidates, key=lambda w: w.load)
```

### 5. Worker 特殊组件

#### 5.1 TaskExecutor（任务执行器）

```python
class TaskExecutor:
    """Worker 任务执行器"""
    
    def __init__(self, task_def: dict):
        self.task = Task.parse(task_def)
        self.agent = None  # 临时 Agent 实例
        self.work_dir = tempfile.mkdtemp()
        
    async def setup(self):
        """初始化执行环境"""
        # 1. 创建临时 Agent Core
        self.agent = AgentCore({
            "llm": load_llm_config(),  # 和 Master 相同配置
            "tools": self.load_tools(self.task.skills_required),
            "memory": TemporaryMemory(self.work_dir)
        })
        
        # 2. 设置系统提示（临时身份）
        self.agent.set_system_prompt(f"""
        你是 PiBot Worker，任务 ID: {self.task.id}
        目标: {self.task.objective}
        可用技能: {', '.join(self.task.skills_required)}
        工作目录: {self.work_dir}
        
        你需要使用可用技能完成任务。
        如果任务需要，使用 code_writer 编写代码。
        完成后返回结构化结果。
        """)
    
    async def execute(self) -> Result:
        """执行任务"""
        try:
            # 使用 Agent Core 运行任务
            result = await self.agent.run(self.task)
            
            return {
                "task_id": self.task.id,
                "status": "success",
                "result": result.summary,
                "artifacts": result.artifacts,
                "work_dir": self.work_dir
            }
            
        except Exception as e:
            return {
                "task_id": self.task.id,
                "status": "failed",
                "error": str(e)
            }
    
    async def cleanup(self):
        """清理资源"""
        # 1. 关闭 Agent Core
        if self.agent:
            await self.agent.shutdown()
        
        # 2. 删除工作目录（包含所有临时文件和记忆）
        shutil.rmtree(self.work_dir, ignore_errors=True)
        
        # 3. 删除任务文件
        self.task.file.unlink(missing_ok=True)
        
        logger.info(f"Worker memory cleared for task {self.task.id}")
```

#### 5.2 CodeAgent（代码编写 Agent）

```python
class CodeAgent:
    """专门用于编写和执行代码的 Agent"""
    
    async def write_code(self, objective: str, context: str) -> CodeResult:
        """编写代码完成任务"""
        
        prompt = f"""
        编写 Python 代码完成以下任务：
        
        目标: {objective}
        上下文: {context}
        
        要求：
        1. 代码完整、可运行
        2. 包含必要的错误处理
        3. 使用标准库，如需第三方库请说明
        4. 添加注释说明关键步骤
        
        返回格式：
        ```python
        # 代码
        ```
        
        执行说明：
        - 输入: xxx
        - 输出: xxx
        - 副作用: xxx（如有文件操作）
        """
        
        response = await self.llm.ask(prompt)
        code = self.extract_code(response)
        
        # 保存代码到临时文件
        code_file = self.work_dir / f"task_{self.task_id}.py"
        code_file.write_text(code)
        
        # 执行代码
        result = await self.execute_code(code_file)
        
        return CodeResult(
            code=code,
            file=code_file,
            output=result.stdout,
            errors=result.stderr,
            success=result.returncode == 0
        )
    
    async def execute_code(self, code_file: Path) -> ExecutionResult:
        """在沙箱中执行代码"""
        # 使用 subprocess 在隔离环境执行
        proc = await asyncio.create_subprocess_exec(
            "python3", str(code_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.work_dir
        )
        
        stdout, stderr = await proc.communicate()
        
        return ExecutionResult(
            returncode=proc.returncode,
            stdout=stdout.decode(),
            stderr=stderr.decode()
        )
```

### 6. 共享组件（Master 和 Worker）

#### 6.1 LLM API（统一接口）

```python
class LLMClient:
    """统一 LLM 接口 - Master 和 Worker 共享"""
    
    def __init__(self, config):
        self.provider = config.provider  # openai, anthropic, google, etc.
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.model = config.model
    
    async def ask(self, prompt: str, system: str = None) -> str:
        """简单问答"""
        pass
    
    async def plan(self, system: str, objective: str) -> Plan:
        """生成执行计划"""
        pass
    
    async def chat(self, messages: list) -> Message:
        """对话模式"""
        pass
```

#### 6.2 工具集（共享工具）

```python
# tools/web_fetch.py - Master 和 Worker 共享
class WebFetchTool:
    """网页抓取工具"""
    
    async def fetch(self, url: str, method: str = "GET", headers: dict = None) -> FetchResult:
        """抓取网页"""
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers) as resp:
                return FetchResult(
                    status=resp.status,
                    content=await resp.text(),
                    headers=dict(resp.headers)
                )

# tools/code_writer.py - Master 和 Worker 共享
class CodeWriterTool:
    """代码编写工具"""
    
    async def write(self, language: str, objective: str, context: str = "") -> CodeResult:
        """编写代码"""
        # 使用 LLM 生成代码
        code = await self.llm.generate_code(objective, context, language)
        
        # 保存并验证
        code_file = self.save_code(code, language)
        
        return CodeResult(code=code, file=code_file)
    
    async def execute(self, code_file: Path, language: str = "python") -> ExecutionResult:
        """执行代码"""
        if language == "python":
            return await self.execute_python(code_file)
        elif language == "shell":
            return await self.execute_shell(code_file)
```

### 7. 状态管理

#### 7.1 Master 状态（持久）

```python
class MasterState:
    """Master 持久化状态"""
    
    def __init__(self):
        self.tasks = {}  # 所有任务历史
        self.workers = {}  # Worker 状态
        self.conversations = []  # 对话历史
    
    def save_task(self, task: Task):
        """保存任务"""
        self.tasks[task.id] = task
        self.persist()
    
    def persist(self):
        """持久化到磁盘"""
        with open("master_state.json", "w") as f:
            json.dump(self.to_dict(), f)
```

#### 7.2 Worker 状态（临时）

```python
class WorkerState:
    """Worker 临时状态 - 任务结束销毁"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.current_step = 0
        self.results = []
        self.memory = []  # 临时记忆，不持久化
    
    def update(self, step: Step, result: Result):
        """更新状态"""
        self.current_step += 1
        self.results.append({"step": step, "result": result})
        self.memory.append(f"Step {self.current_step}: {result.summary}")
    
    def cleanup(self):
        """清理所有状态"""
        self.results = []
        self.memory = []
        # 删除工作目录
        shutil.rmtree(self.work_dir, ignore_errors=True)
```

### 8. 通信协议

#### 8.1 任务分派

```
Master                          Worker
  │                               │
  ├─ 1. 生成 task_001.json ───────┤
  │   (任务定义)                   │
  │                               │
  ├─ 2. scp task_001.json ───────►│
  │   复制到 Worker /tmp/          │
  │                               │
  ├─ 3. ssh "python3              │
  │      worker_executor.py       │
  │      task_001.json" ─────────►│
  │   启动执行器                   │
  │                               │
  │◄─ 4. 异步执行 ────────────────┤
  │                               │
  ├─ 5. 轮询检查状态 ────────────►│
  │   check_task_status(task_id)  │
  │                               │
  │◄─ 6. 返回结果 ────────────────┤
  │   result_001.json             │
```

#### 8.2 消息格式

```json
// 任务定义 (task_{id}.json)
{
    "version": "3.0",
    "task_id": "task_20250219_001",
    "created_at": "2026-02-19T08:00:00Z",
    "objective": "下载并分析 https://example.com/data.csv",
    "context": "用户需要数据的统计摘要",
    "type": "complex",
    "skills_required": ["web_fetch", "code_writer", "data_analysis"],
    "worker_id": "worker_2",
    "ttl": 300,
    "timeout_action": "fail",
    "retry_count": 0,
    "max_retries": 2,
    "master_callback": "http://<MASTER_IP>:5000/api/worker/result"
}

// 执行结果 (result_{id}.json)
{
    "version": "3.0",
    "task_id": "task_20250219_001",
    "worker_id": "worker_2",
    "status": "success",
    "result": {
        "summary": "成功下载并分析了 1000 行数据",
        "details": "平均价格: $50, 最高: $200, 最低: $10",
        "data": {"rows": 1000, "avg": 50, "max": 200, "min": 10}
    },
    "artifacts": [
        "/tmp/task_001/analysis_report.txt",
        "/tmp/task_001/price_chart.png"
    ],
    "code_executed": "import pandas as pd\n...",
    "duration": 45.2,
    "started_at": "2026-02-19T08:00:05Z",
    "completed_at": "2026-02-19T08:00:50Z",
    "logs": ["Downloaded 15KB", "Parsed 1000 rows", "Generated chart"]
}
```

### 9. 实现路线图

#### Phase 1: 基础架构
1. **统一 LLM API** - 支持多提供商
2. **Agent Core** - 工具调用和状态管理
3. **工具注册系统** - 可扩展的工具架构

#### Phase 2: Master 完善
1. **TaskPlanner** - 任务分析和规划
2. **WorkerPool** - Worker 管理和调度
3. **状态持久化** - 任务历史记录

#### Phase 3: Worker 实现
1. **TaskExecutor** - 任务执行引擎
2. **CodeAgent** - 代码编写和执行
3. **资源清理** - 临时资源管理

#### Phase 4: 通信和集成
1. **任务传输** - 文件传输协议
2. **状态查询** - 远程状态检查
3. **结果收集** - 异步结果收集

#### Phase 5: 优化和测试
1. **错误处理** - 重试和容错机制
2. **性能优化** - 并行执行优化
3. **安全加固** - 代码沙箱和权限控制
