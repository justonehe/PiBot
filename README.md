# PiBot V3: Distributed Python Agent System 🤖 (Beta)

A lightweight, robust distributed agent system running on Raspberry Pi, designed for stability and modern interactions.

![Status](https://img.shields.io/badge/status-beta-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-yellow.svg)
![Platform](https://img.shields.io/badge/platform-RabbitMQ%20%7C%20Flask-green.svg)

## 🌟 Features

- **Dual-Node Architecture**:
  - **Master (Hub)**: Web-based dashboard (Flask), LLM integration (Volcengine), Kiosk display.
  - **Worker (Executor)**: Silent task runner listening to file queues via SCP.
- **Dual-Interface**:
  - **Desktop Kiosk**: Designed for 7-inch Raspberry Pi screens (Clock, Weather, Todo).
  - **Mobile Web App**: `/mobile` route optimized for phone control.
- **Robustness**: Systemd-ready startup scripts, threaded Flask server, and self-healing Kiosk mode.
- **Zero-MQ**: Uses SCP/SSH for communication. No complex message broker required.

## 📂 Structure

```
.
├── src/
│   ├── master_hub.py       # Master Node: Flask Web Server & Logic
│   ├── worker_watcher.py   # Worker Node: File Queue Listener
│   ├── run_master.sh       # Robust Startup for Master
│   └── run_dashboard.sh    # Robust Startup for Kiosk Browser
├── docs/
│   ├── architecture_design.md
│   ├── task.md
│   └── walkthrough.md
└── README.md
```

## 🚀 Quick Start

### 1. Master Node

Deploy `src/` to your Master Pi (e.g. `192.168.10.113`).

```bash
# Install Dependencies
pip3 install flask requests openai

# Run Service
./run_master.sh

# Run Kiosk Display
./run_dashboard.sh
```

### 2. Worker Node

Deploy `worker_watcher.py` to your Worker Pi (e.g. `192.168.10.66`).

```bash
# Setup Directory
mkdir -p ~/inbox ~/outbox

# Run Watcher
python3 worker_watcher.py
```

### 3. Usage

- **Desktop**: Look at the Master Pi screen.
- **Mobile**: Scan the QR code or visit `http://<MASTER_IP>:5000/mobile`.

## 🛠️ Configuration

Edit `master_hub.py` to set your:

- LLM API Keys (Volcengine)
- Worker IP Address
- Location for Weather

## 📝 License

MIT
