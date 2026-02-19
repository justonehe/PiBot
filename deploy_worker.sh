#!/bin/bash
# PiBot V3 Worker Deployment Script
# Run this on the Worker (e.g. <WORKER_IP>)

set -e

echo "==============================================="
echo "PiBot V3 Worker Deployment"
echo "==============================================="
echo ""

# Configuration - CHANGE THESE VALUES
WORKER_IP="${WORKER_IP:-127.0.0.1}"
WORKER_ID="${WORKER_ID:-worker-1}"
INSTALL_DIR="$HOME/pibot-worker"

echo "Installing to: $INSTALL_DIR"
echo "Worker ID: $WORKER_ID"
echo "Worker IP: $WORKER_IP"
echo ""

# Create directory
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "[1/6] Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

echo ""
echo "[2/6] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo ""
echo "[3/6] Installing Python packages..."
pip install --upgrade pip
pip install flask aiohttp openai

echo ""
echo "[4/6] Setting up directory structure..."
mkdir -p skills logs

echo ""
echo "[5/6] Creating configuration files..."

# Create .env file if not exists
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# PiBot V3 Worker Configuration
# Copy your actual API key here
VOLC_API_KEY=your_volc_api_key_here
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=doubao-seed-code
WORKER_ID=worker-1
EOF
    echo "Created .env file - Please edit with your actual API key!"
fi

# Create worker soul
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
5. Do not ask for clarification - make reasonable assumptions

## Constraints
- You have no persistent memory
- Each task is independent
- You only have access to your local filesystem
- You can use specified skills only

## Response Format
Always return results in this format:
{
  "success": true/false,
  "data": { ... },
  "output": "Human-readable summary"
}
EOF

# Create systemd service file
cat > pibot-worker.service << EOF
[Unit]
Description=PiBot V3 Worker ($WORKER_ID)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python worker_task_executor.py --port 5000 --worker-id $WORKER_ID
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/worker.log
StandardError=append:$INSTALL_DIR/logs/worker.log

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "[6/6] Creating startup script..."
cat > start_worker.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 worker_task_executor.py --port 5000 --worker-id worker-1
EOF
chmod +x start_worker.sh

cat > start_worker_bg.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
nohup python3 worker_task_executor.py --port 5000 --worker-id worker-1 > logs/worker.log 2>&1 &
echo "Worker started in background. Check logs/worker.log"
EOF
chmod +x start_worker_bg.sh

echo ""
echo "==============================================="
echo "Deployment Complete!"
echo "==============================================="
echo ""
echo "Next steps:"
echo "1. Copy Python files to $INSTALL_DIR:"
echo "   - agent_core.py"
echo "   - llm_client.py"
echo "   - tool_registry.py"
echo "   - worker_task_executor.py"
echo "   - skills/ directory"
echo ""
echo "2. Edit .env file and add your VOLC_API_KEY"
echo ""
echo "3. Start the worker:"
echo "   ./start_worker.sh          # Foreground"
echo "   ./start_worker_bg.sh       # Background"
echo ""
echo "4. (Optional) Install systemd service:"
echo "   sudo cp pibot-worker.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable pibot-worker"
echo "   sudo systemctl start pibot-worker"
echo ""
echo "5. Test the worker:"
echo "   curl http://$WORKER_IP:5000/health"
echo ""
