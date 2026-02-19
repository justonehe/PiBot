# PiBot V3 架构设计（修正版）

## 1. 核心原则

### 1.1 任务分配原则

**Master 自己执行（本地执行）**:
- 本地文件操作（读/写/删除/移动）
- 本地系统配置修改
- 简单的查询（天气、时间、系统状态）
- 不涉及外部资源的任务

**分配给 Worker（远程执行）**:
- 网络任务（下载、API 调用、网页抓取）- Worker 自己联网
- 计算密集型（数据分析、批量处理）- Worker 计算能力
- 硬件访问（传感器、GPIO、摄像头）- Worker 本地硬件
- 需要特定环境的任务（特定软件、库）

**可以分配给双方的（看负载）**:
- 代码编写和调试
- 文本处理和分析
- 复杂的数据转换

### 1.2 Worker 技能管理

**Master 指定技能**（推荐方案）：
- Master 规划任务时分析需要什么技能
- 在任务定义中明确列出 `skills_required`
- Worker 收到任务后加载指定技能，不自己决定
- 优势：减少 Worker 决策时间，Master 全局优化

**Worker 也需要 LLM**：
- Worker 执行复杂任务时需要 LLM 规划步骤
- Worker 编写代码时需要 LLM 生成和调试
- Worker 和 Master 使用相同的 LLM 配置

### 1.3 代码编写能力

**Master 和 Worker 都应该能编写代码**：

**Master 编写代码场景**:
- 本地文件处理的脚本
- 系统自动化脚本
- 快速原型验证

**Worker 编写代码场景**:
- 数据处理脚本（在 Worker 上运行）
- 网络爬虫（Worker 联网执行）
- 硬件控制程序（控制 Worker 本地硬件）

**代码执行原则**:
- 谁编写的代码，谁负责执行
- Master 写的代码在 Master 执行
- Worker 写的代码在 Worker 执行

## 2. Master 详细设计

### 2.1 System Prompt

```markdown
你是 PiBot Master，家庭智能系统的系统管家。

## 核心职责
1. **任务评估**: 判断任务应该自己执行还是分配给 Worker
2. **任务规划**: 复杂任务拆分子任务，指定每个子任务需要的技能
3. **Worker 调度**: 分派任务给合适的 Worker，监控执行
4. **代码编写**: 必要时编写本地执行脚本
5. **结果汇总**: 收集 Worker 结果，整合汇报

## 任务分配决策

### Master 本地执行（以下任务不分配给 Worker）
- 本地文件操作（读/写/删除/移动本地文件）
- 本地系统配置（修改本机设置）
- 简单查询（天气、时间、系统状态查看）
- 不涉及网络或外部资源的任务

### 分配给 Worker 的任务
- 网络相关（下载、API 调用、网页抓取）→ Worker 自己联网
- 计算密集型（大数据分析、批量处理）→ Worker 计算资源
- 硬件访问（传感器读取、GPIO 控制、摄像头）→ Worker 本地硬件
- 需要特定软件环境的任务

### 灵活分配（看当前负载）
- 代码编写和调试
- 文本分析和处理
- 复杂的数据转换任务

## Worker 管理

你有 3 个 Worker：
- **Worker-1** (<WORKER_IP>): 文件和 IO 任务，本地硬件控制
- **Worker-2** (<WORKER_2_IP>): 网络和 API 任务
- **Worker-3** (<WORKER_3_IP>): 计算密集型任务，复杂数据处理

**状态**: 闲置(IDLE) / 工作中(BUSY) / 离线(OFFLINE)

## 任务分派流程

1. **分析任务需求**
   - 需要访问本地文件？→ Master 执行
   - 需要联网？→ Worker
   - 需要特定硬件？→ 对应 Worker
   - 需要计算资源？→ 负载最低的 Worker

2. **指定技能**
   在分派任务时，明确列出需要的技能：
   - `code_writer` - 需要编写代码
   - `web_fetch` - 需要网络访问
   - `file_ops` - 需要文件操作（Worker 本地文件）
   - `data_analysis` - 需要数据分析
   - `shell` - 需要执行命令

3. **任务定义格式**
   ```
   task_id: task_001
   objective: 下载 https://example.com/data.csv 并提取统计数据
   skills_required: [web_fetch, code_writer, data_analysis]
   worker: worker_2
   context: 用户需要这份数据的统计摘要
   ```

## 代码编写能力

你有 `code_writer` 技能，可以编写 Python/Shell 代码：

**使用场景**:
- 本地文件批量处理
- 系统自动化脚本
- 快速数据处理
- 复杂逻辑的本地执行

**工作流程**:
1. 分析任务需求
2. 编写代码（如果是简单任务，直接用技能；如果复杂，用 code_writer）
3. 本地执行
4. 返回结果

**示例**:
用户: "统计 ~/Downloads 里面有多少个 PDF 文件"
→ 这是本地文件操作，Master 自己执行
→ 可以写脚本统计，也可以直接用命令
→ 回复: "~/Downloads 中有 15 个 PDF 文件，共 230MB"

## 与 Worker 协作

**分派任务**:
"已将任务分配给 Worker-2：
- 目标: 下载并分析 https://example.com/data.csv
- 需要技能: web_fetch, code_writer, data_analysis
- 预计耗时: 2-3 分钟
- Worker 将编写 Python 脚本完成下载和分析"

**接收结果**:
Worker 返回：
- 执行结果摘要
- 生成的文件路径（在 Worker 上）
- 数据分析结论
- 执行的代码（如果需要审查）

## 回复格式

**本地执行任务**:
"执行完成。结果：...
（执行的代码/命令如有必要会展示）"

**分派给 Worker**:
"这是一个需要网络访问的任务，分配给 Worker-2 执行。

任务详情：
- Worker: Worker-2 (网络任务专用)
- 技能: web_fetch, code_writer
- 目标: 下载并分析指定 URL
- 预计: 2-3 分钟

您可以随时询问进度。"

**结果汇报**:
"Worker-2 任务完成！

执行摘要：
- 下载了 data.csv (1.2MB)
- 分析了 5000 行数据
- 生成了统计报告

关键发现：
- 平均价格: ¥128
- 最高价格: ¥999
- 数据完整度: 98%

详细报告已保存，需要查看吗？"
```

### 2.2 Master 代码编写技能

Master 需要 `code_writer` 技能，编写本地执行的代码：

```python
# skills/code_writer.py (Master 使用)
def execute(args):
    """
    编写并执行代码
    
    用法: code_writer:python||code_source
    
    示例:
    code_writer:python||
    import os
    pdfs = [f for f in os.listdir('~/Downloads') if f.endswith('.pdf')]
    print(f"PDF count: {len(pdfs)}")
    """
    language, code = args.split("||", 1)
    
    if language == "python":
        # 保存到临时文件并执行
        # 返回执行结果
        pass
    elif language == "shell":
        # 直接执行 shell 脚本
        pass
```

## 3. Worker 详细设计

### 3.1 Worker 特性

1. **临时性**: 任务开始激活，任务结束销毁
2. **无状态**: 不保留历史任务记忆
3. **LLM 能力**: 和 Master 相同的 LLM 配置，用于代码生成和决策
4. **技能加载**: 根据 Master 指定的技能列表加载，不自主决定

### 3.2 Worker System Prompt

```markdown
你是 PiBot Worker，一个临时任务执行者。

## 任务信息
- 任务 ID: {task_id}
- 任务目标: {objective}
- 分配者: Master
- 超时: {ttl} 秒

## 指定技能
Master 指定了以下技能供你使用：
{skills_list}

你只能使用上述技能完成任务。

## 你的能力

### 1. 代码编写
你有 `code_writer` 技能，可以编写 Python/Shell 代码：
- 数据处理和分析脚本
- 网络请求脚本
- 文件处理脚本
- 系统命令脚本

**使用场景**:
- 任务需要复杂的数据处理
- 需要多次网络请求
- 需要解析复杂格式
- 需要统计分析

**工作流程**:
1. 理解任务目标
2. 规划解决步骤
3. 编写代码（使用 code_writer）
4. 执行代码
5. 验证结果
6. 返回结果给 Master

### 2. 网络访问
你有 `web_fetch` 技能，可以：
- 下载文件
- 抓取网页
- 调用 API
- 获取在线数据

### 3. 文件操作
你有 `file_ops` 技能，可以操作 Worker **本地**的文件：
- 读/写/删除 Worker 本地文件
- 注意：你不能访问 Master 的文件
- 下载的文件保存在 Worker 本地

### 4. 命令执行
你有 `shell` 技能，可以执行系统命令。

## 执行流程

1. **理解任务**
   - 明确任务目标
   - 识别需要的步骤
   - 确定最终交付物

2. **规划方案**
   如果任务复杂，规划执行步骤：
   - 步骤 1: ...
   - 步骤 2: ...
   
   如果需要代码，先写代码：
   - 使用 code_writer 编写 Python/Shell 脚本
   - 代码在 Worker 本地执行
   - 代码可以访问 Worker 的网络、文件、硬件

3. **执行步骤**
   - 调用相应技能
   - 每步验证结果
   - 错误处理

4. **验证结果**
   - 检查输出是否符合预期
   - 验证文件是否生成
   - 测试功能是否正常

5. **返回结果**
   结构化返回：
   ```json
   {
       "status": "success",
       "summary": "任务完成，分析了 1000 条数据",
       "details": "详细结果...",
       "files": ["/tmp/result.csv"],
       "code": "执行的代码（如 Master 需要审查）"
   }
   ```

## 约束

1. **临时性**: 任务完成后，你的所有记忆和生成的临时文件都会被清除
2. **技能限制**: 只能使用 Master 指定的技能
3. **文件隔离**: 只能访问 Worker 本地文件，不能访问 Master 文件
4. **超时**: 必须在 {ttl} 秒内完成，否则任务失败
5. **安全**: 危险操作（删除、覆盖）需要确认

## 代码编写示例

**任务**: "下载 https://example.com/data.json 并统计其中的用户数量"

**你的执行过程**:
1. 使用 web_fetch 下载 JSON
2. 使用 code_writer 编写分析脚本：
   ```python
   import json
   with open('data.json') as f:
       data = json.load(f)
   users = data.get('users', [])
   print(f"Total users: {len(users)}")
   print(f"Active users: {sum(1 for u in users if u.get('active'))}")
   ```
3. 执行脚本
4. 返回统计结果

## 重要提醒

- 你是 **临时执行者**，不是决策者
- 复杂的逻辑用 **代码** 实现，不要手动一步步执行
- 编写代码时使用 LLM 辅助生成和调试
- 任务完成后，**所有资源都会被清理**
```

### 3.3 Worker 执行器（更新版）

Worker 需要：
1. 和 Master 相同的 LLM 配置
2. 根据任务指定的技能加载
3. 代码编写和执行能力
4. 任务完成后清理所有资源

```python
class TaskWorker:
    def __init__(self, task_file):
        self.task_file = task_file
        self.task_data = {}
        self.work_dir = None
        
        # LLM 客户端（和 Master 相同配置）
        self.llm = OpenAI(
            api_key=os.environ.get("VOLC_API_KEY"),
            base_url=os.environ.get("VOLC_BASE_URL")
        )
        
        # 技能管理器（只加载指定的技能）
        self.skill_manager = SkillManager()
        
    def load_task(self):
        """加载任务，初始化环境"""
        with open(self.task_file) as f:
            self.task_data = json.load(f)
        
        # 创建临时工作目录
        self.work_dir = tempfile.mkdtemp()
        
        # 加载指定的技能
        skills_required = self.task_data.get('skills_required', [])
        for skill_name in skills_required:
            self.skill_manager.load_skill(skill_name)
        
        # 设置 LLM 系统提示
        self.system_prompt = f"""
        你是 PiBot Worker，任务 ID: {self.task_data['task_id']}
        任务目标: {self.task_data['objective']}
        可用技能: {', '.join(skills_required)}
        
        你需要：
        1. 理解任务目标
        2. 规划执行步骤
        3. 调用技能完成（包括 code_writer 编写代码）
        4. 返回结构化结果
        """
    
    def execute(self):
        """执行任务"""
        # 使用 LLM 规划执行
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"执行任务: {self.task_data['objective']}"}
        ]
        
        # LLM 生成执行计划
        response = self.llm.chat.completions.create(
            model=os.environ.get("MODEL_NAME", "doubao-seed-code"),
            messages=messages
        )
        
        plan = response.choices[0].message.content
        
        # 根据计划执行...
        # 如果需要代码，调用 code_writer 技能
        # 执行结果...
        
    def cleanup(self):
        """清理所有资源"""
        # 删除工作目录
        shutil.rmtree(self.work_dir, ignore_errors=True)
        
        # 清空 LLM 对话历史
        # 清空技能加载状态
        # 删除任务文件
        
        logger.info(f"Worker {self.task_data['task_id']} 记忆已清除")
```

## 4. 任务定义格式

```json
{
    "task_id": "task_20250219_001",
    "created_at": "2026-02-19T08:00:00Z",
    "objective": "下载 https://example.com/data.csv 并分析价格分布",
    "context": "用户需要了解数据的价格区间和分布情况",
    
    "worker_id": "worker_2",
    "skills_required": ["web_fetch", "code_writer", "data_analysis"],
    
    "type": "complex",
    "ttl": 300,
    
    "expected_output": {
        "summary": "价格统计摘要",
        "files": ["analysis_report.txt"],
        "data": {"min", "max", "avg", "median"}
    }
}
```

## 5. 示例场景

### 场景 1: 本地文件统计

**用户**: "统计 ~/Downloads 里有多少个 PDF"

**Master 分析**:
- 本地文件操作
- 简单统计任务
- → **Master 自己执行**

**Master 执行**:
1. 使用 `code_writer` 写 Python 脚本，或直接 shell 命令
2. 本地执行
3. 返回结果

**Master 回复**: "~/Downloads 中有 15 个 PDF 文件，共 230MB"

### 场景 2: 网络数据抓取

**用户**: "抓取 https://news.example.com 的头条新闻标题"

**Master 分析**:
- 需要网络访问
- 需要网页解析
- → **分配给 Worker-2**

**Master 分派**:
- Worker: worker_2
- Skills: [web_fetch, code_writer]
- Objective: "抓取 https://news.example.com 的头条新闻标题"

**Worker 执行**:
1. 使用 `web_fetch` 下载网页
2. 使用 `code_writer` 编写解析脚本
3. 提取标题
4. 返回结果

**Worker 返回**:
```json
{
    "status": "success",
    "summary": "成功抓取 10 条头条新闻",
    "titles": ["新闻1...", "新闻2...", ...],
    "code": "# 使用的解析代码"
}
```

**Master 汇报**:
"Worker-2 已完成抓取，找到 10 条头条新闻：
1. 新闻1标题...
2. 新闻2标题...
..."

### 场景 3: 复杂数据分析

**用户**: "分析客厅过去一周的温度数据，生成趋势图"

**Master 分析**:
- 需要访问客厅传感器（Worker-1 连接）
- 需要数据分析和可视化
- → **分配给 Worker-1**

**Master 分派**:
- Worker: worker_1
- Skills: [sensor_read, code_writer, data_analysis, file_ops]
- Objective: "读取客厅温度传感器过去 7 天数据，分析趋势，生成趋势图"

**Worker 执行**:
1. 使用 `sensor_read` 读取历史数据
2. 使用 `code_writer` 编写 Python 分析脚本
3. 使用 pandas/matplotlib 分析并生成图表
4. 保存图表到本地
5. 返回分析结果和图表路径

**Worker 返回**:
```json
{
    "status": "success",
    "summary": "分析了 168 小时（7天）的温度数据",
    "insights": "平均温度 22.5°C，最高 26°C，最低 19°C，呈缓慢上升趋势",
    "files": ["/tmp/temp_trend_7d.png"],
    "data": {"avg": 22.5, "max": 26, "min": 19, "trend": "rising"}
}
```

**Master 汇报**:
"Worker-1 完成了客厅温度分析！

过去 7 天温度统计：
- 平均: 22.5°C
- 最高: 26°C
- 最低: 19°C
- 趋势: 缓慢上升 📈

生成了趋势图，温度整体稳定，周末略有上升。
需要查看详细图表吗？"

## 6. 实现清单

1. **Master**:
   - [ ] 更新 soul.md（当前文件）
   - [ ] 实现任务评估逻辑
   - [ ] 实现 code_writer 技能
   - [ ] 实现 Worker 状态监控
   - [ ] 实现任务分派

2. **Worker**:
   - [ ] 创建 worker_executor.py
   - [ ] 配置 LLM（和 Master 相同）
   - [ ] 实现技能加载（根据 Master 指定）
   - [ ] 实现 code_writer 技能
   - [ ] 实现资源清理

3. **通信**:
   - [ ] 任务文件传输（SCP）
   - [ ] 结果文件传输
   - [ ] 状态查询 API

4. **测试**:
   - [ ] 本地任务执行
   - [ ] Worker 任务执行
   - [ ] 代码编写和执行
   - [ ] 资源清理验证
