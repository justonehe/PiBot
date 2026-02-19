# PiBot V3 部署指南 (单 Worker)

## 概述

本指南帮助您将 PiBot V3 Master-Worker 架构部署到生产环境。

**当前配置**:
- **Master**: <MASTER_IP> (主控)
- **Worker**: <WORKER_IP> (单台 Raspberry Pi)

## 部署步骤

### 第一步：部署 Worker (<WORKER_IP>)

在 Worker 设备上执行以下操作：

```bash
# 1. SSH 登录到 Worker
ssh pi@<WORKER_IP>

# 2. 创建工作目录
mkdir -p ~/pibot-worker
cd ~/pibot-worker

# 3. 复制以下文件到该目录 (通过 SCP 或手动复制):
# - agent_core.py
# - llm_client.py  
# - tool_registry.py
# - worker_task_executor.py
# - skills/ 目录 (包含所有技能文件)

# 4. 安装依赖
sudo apt-get update
sudo apt-get install -y python3-pip
pip3 install flask aiohttp openai

# 5. 创建环境配置文件
cat > .env << 'EOF'
VOLC_API_KEY=your_actual_api_key_here
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=doubao-seed-code
WORKER_ID=worker-1
EOF

# 6. 创建 worker 系统提示
cat > worker_soul.md << 'EOF'
# PiBot Worker Agent

You are a Worker agent in the PiBot V3 system.

## Your Role
Execute tasks assigned by the Master agent efficiently and accurately.

## Guidelines
1. Execute tasks to the best of your ability
2. Use the provided tools/skills to complete the task
3. Return structured results in JSON format
4. Report errors clearly with context

## Constraints
- You have no persistent memory
- Each task is independent
- You only have access to your local filesystem
EOF

# 7. 启动 Worker
python3 worker_task_executor.py --port 5000 --worker-id worker-1

# 后台运行方式:
nohup python3 worker_task_executor.py --port 5000 --worker-id worker-1 > worker.log 2>&1 &
```

### 第二步：配置 Systemd 自动启动 (Worker)

创建 systemd 服务文件实现开机自动启动：

```bash
# 在 Worker 上执行
sudo tee /etc/systemd/system/pibot-worker.service << 'EOF'
[Unit]
Description=PiBot V3 Worker
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pibot-worker
Environment="VOLC_API_KEY=your_actual_api_key_here"
Environment="VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3"
Environment="MODEL_NAME=doubao-seed-code"
Environment="WORKER_ID=worker-1"
ExecStart=/usr/bin/python3 /home/pi/pibot-worker/worker_task_executor.py --port 5000 --worker-id worker-1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动服务
sudo systemctl daemon-reload
sudo systemctl enable pibot-worker
sudo systemctl start pibot-worker

# 检查状态
sudo systemctl status pibot-worker
```

### 第三步：验证 Worker 运行

```bash
# 测试 Worker 是否响应
curl http://<WORKER_IP>:5000/health

# 应该返回:
# {
#   "status": "healthy",
#   "worker_id": "worker-1",
#   "current_task": null
# }
```

### 第四步：部署 Master

在 Master 设备 (<MASTER_IP>) 上：

```bash
# 1. 进入 PiBot 目录
cd ~/pibot

# 2. 安装新依赖 (如未安装)
pip3 install aiohttp

# 3. 复制新文件到目录 (这些文件已创建好):
# - agent_core.py
# - llm_client.py
# - tool_registry.py
# - master_components.py

# 4. 更新环境变量
cat >> .env << 'EOF'

# Worker Configuration (单 Worker)
WORKER_1_IP=<WORKER_IP>
EOF

# 5. 更新 soul.md (已创建好新的 soul.md)
cp soul.md soul.md.backup
cp soul_new.md soul.md  # 或使用本目录的 soul.md

# 6. 测试连接
python3 << 'EOF'
import asyncio
from master_components import create_default_worker_pool

async def test():
    pool = create_default_worker_pool()
    health = await pool.check_all_workers_health()
    for worker_id, is_healthy in health.items():
        status = "✓" if is_healthy else "✗"
        print(f"{worker_id}: {status}")
    await pool.close()

asyncio.run(test())
EOF
```

### 第五步：测试完整流程

```bash
# 运行集成测试
python3 test_integration.py
```

## 文件清单

需要复制到 Worker (<WORKER_IP>) 的文件：

```
~/pibot-worker/
├── agent_core.py              # 核心代理循环
├── llm_client.py             # LLM 客户端
├── tool_registry.py          # 工具注册表
├── worker_task_executor.py   # Worker 执行器
├── worker_soul.md           # Worker 系统提示
├── .env                      # 环境变量
├── skills/                   # 技能目录
│   ├── core.py
│   ├── web_fetch.py
│   ├── file_ops.py
│   └── ...
└── logs/                     # 日志目录
```

Master 需要的文件（已在此目录）：

```
~/pibot/
├── master_hub.py             # 主程序 (现有)
├── agent_core.py             # 新增
├── llm_client.py            # 新增
├── tool_registry.py         # 新增
├── master_components.py     # 新增 (TaskPlanner + WorkerPool)
├── soul.md                  # 新的系统提示
└── test_integration.py      # 测试脚本
```

## 常用命令

### Worker 管理

```bash
# 检查 Worker 状态
sudo systemctl status pibot-worker

# 查看日志
sudo journalctl -u pibot-worker -f
tail -f ~/pibot-worker/worker.log

# 重启 Worker
sudo systemctl restart pibot-worker

# 停止 Worker
sudo systemctl stop pibot-worker
```

### Master 管理

```bash
# 启动 Master
cd ~/pibot
python3 master_hub.py

# 检查 Worker 连接
python3 << 'EOF'
import asyncio
from master_components import create_default_worker_pool

async def check():
    pool = create_default_worker_pool()
    status = pool.get_status_summary()
    print(f"Workers: {status['total']}")
    print(f"  Idle: {status['idle']}")
    print(f"  Busy: {status['busy']}")
    print(f"  Offline: {status['offline']}")
    await pool.close()

asyncio.run(check())
EOF
```

## 故障排除

### Worker 无法连接

```bash
# 1. 检查 Worker 是否在运行
curl http://<WORKER_IP>:5000/health

# 2. 检查防火墙
sudo ufw status
sudo ufw allow 5000/tcp

# 3. 检查端口占用
sudo lsof -i :5000

# 4. 查看详细日志
sudo journalctl -u pibot-worker -n 50
```

### API Key 错误

```bash
# 检查环境变量是否设置
echo $VOLC_API_KEY

# 检查 .env 文件
cat ~/pibot-worker/.env
```

### 导入错误

```bash
# 安装缺失的依赖
pip3 install flask aiohttp openai

# 检查 Python 版本
python3 --version  # 需要 3.9+
```

## 安全建议

1. **限制 Worker 访问**
   ```bash
   # 仅允许 Master IP 访问 Worker
   sudo ufw allow from <MASTER_IP> to any port 5000
   ```

2. **使用非 root 用户运行**
   - Worker 和 Master 都应使用普通用户运行

3. **保护 API Key**
   - 确保 .env 文件权限正确: `chmod 600 .env`
   - 不要将 API Key 提交到 Git

4. **日志清理**
   ```bash
   # 设置日志轮转
   sudo logrotate -f /etc/logrotate.d/pibot-worker
   ```

## 扩展 Worker

如果您以后想添加更多 Worker：

```bash
# 1. 在新 Worker 上重复第一步部署

# 2. 在 Master 上添加新 Worker IP
echo "WORKER_2_IP=<WORKER_2_IP>" >> ~/pibot/.env
echo "WORKER_3_IP=<WORKER_3_IP>" >> ~/pibot/.env

# 3. 重启 Master
# Master 会自动发现新 Worker
```

## 完成检查清单

- [ ] Worker 代码已复制到 <WORKER_IP>
- [ ] Worker 依赖已安装 (flask, aiohttp, openai)
- [ ] Worker .env 文件已配置 API Key
- [ ] Worker 已成功启动 (`curl http://<WORKER_IP>:5000/health` 返回 200)
- [ ] Master 新文件已就位
- [ ] Master .env 已添加 WORKER_1_IP=<WORKER_IP>
- [ ] 集成测试通过 (`python3 test_integration.py`)

## 支持

如有问题：
1. 查看 Worker 日志: `sudo journalctl -u pibot-worker -f`
2. 查看 Master 日志: `tail -f ~/pibot/logs/master_*.log`
3. 测试连接: `curl http://<WORKER_IP>:5000/health`
