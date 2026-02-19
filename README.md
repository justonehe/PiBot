# PiBot V3: Master-Worker Distributed Agent System 🤖

[![Status](https://img.shields.io/badge/status-production-green.svg)](https://github.com/justonehe/PiBot)
[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com/justonehe/PiBot/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)

A production-ready distributed agent system with Master-Worker architecture, designed for smart home automation on Raspberry Pi.

**中文文档**: [docs/README.md](docs/README.md)

---

## 🌟 What's New in v3.0.0

### Major Architecture Upgrade
- **Agent Core**: Implemented based on pi-mono architecture with streaming support
- **Master-Worker Mode**: Distributed task execution with HTTP REST API
- **TaskPlanner**: Intelligent task complexity analysis and routing
- **WorkerPool**: Dynamic worker management and health monitoring
- **Multi-step Execution**: Support for complex multi-step workflows

### Key Features
- 🤖 **Agent Core**: Streaming LLM responses with tool calling
- 🔄 **Task Routing**: Automatic task distribution (Simple → Local, Complex → Worker)
- 📡 **HTTP API**: RESTful communication between Master and Workers
- 🏥 **Health Monitoring**: Real-time worker status and auto-recovery
- 🧠 **Memory Management**: Context-aware conversations
- 🛠️ **Tool System**: Extensible skill-based architecture

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        MASTER NODE                           │
│                    <MASTER_IP>:5000                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────┐   │
│  │  TaskPlanner │───▶│  WorkerPool  │───▶│   Worker    │   │
│  │  Task Analysis│    │  Worker Mgmt │    │  HTTP API   │   │
│  └──────────────┘    └──────────────┘    └──────┬──────┘   │
│         │                                        │          │
│         ▼                                        │          │
│  ┌──────────────┐                               │          │
│  │  Agent Core  │◀── Simple tasks (local)       │          │
│  └──────────────┘                               │          │
└──────────────────────────────────────────────────┼──────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        WORKER NODE                           │
│                    <WORKER_IP>:5000                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
PiBot/
├── master_hub.py              # Master main program (Flask + Agent Core)
├── agent_core.py              # Agent core loop
├── llm_client.py             # LLM client (OpenAI-compatible)
├── tool_registry.py          # Tool registry
├── master_components.py      # TaskPlanner + WorkerPool
├── worker_task_executor.py   # Worker HTTP service
├── test_integration.py       # Integration tests
│
├── skills/                   # Skills directory
├── docs/                     # Documentation
│   ├── README.md            # Detailed docs (Chinese)
│   └── archive/             # Historical docs
│
├── deploy_master.sh         # Master deployment script
├── deploy_worker.sh         # Worker deployment script
├── soul.md                  # Master system prompt
└── README.md                # This file
```

---

## 🚀 Quick Start

### Prerequisites
- **Master**: Raspberry Pi 4 (4GB+ RAM recommended)
- **Worker**: Raspberry Pi Zero 2W or Pi 4
- **OS**: Raspberry Pi OS (64-bit) / Debian 12
- **Python**: 3.11+

### 1. Deploy Worker

```bash
# On Worker
mkdir -p ~/pibot-worker && cd ~/pibot-worker

# Install dependencies
sudo apt-get update && sudo apt-get install -y python3-pip
pip3 install flask aiohttp openai --break-system-packages

# Copy files (agent_core.py, llm_client.py, tool_registry.py, 
#             worker_task_executor.py, worker_soul.md, skills/)

# Create .env
cat > .env << 'EOF'
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=ark-code-latest
WORKER_ID=worker-1
EOF

# Start
python3 worker_task_executor.py --port 5000 --worker-id worker-1
```

### 2. Deploy Master

```bash
# On Master
# Install dependencies
pip3 install flask aiohttp openai --break-system-packages

# Copy files (master_hub.py, components...)

# Create .env
cat > pibot.env << 'EOF'
VOLC_API_KEY=your_api_key
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=ark-code-latest
WORKER_1_IP=<WORKER_IP>
EOF

# Start
python3 master_hub.py
```

---

## 🌐 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Master Web | `http://<MASTER_IP>:5000` | Chat interface |
| Dashboard | `http://<MASTER_IP>:5000/dashboard` | Status dashboard |
| Mobile | `http://<MASTER_IP>:5000/mobile` | Mobile-optimized |
| Worker Health | `http://<WORKER_IP>:5000/health` | Worker status |

---

## 🔄 Version History

### v3.0.0 (2026-02-19)
- ✅ Master-Worker architecture implementation
- ✅ Agent Core with streaming support
- ✅ HTTP REST API communication
- ✅ Multi-step task execution
- ✅ Document consolidation

### v2.x (2026-02-18)
- Bug fixes and optimizations
- Dashboard improvements

---

## 📝 License

MIT License

---

**Version**: v3.0.0  
**Last Updated**: 2026-02-19  
**Maintained by**: justonehe