#!/bin/bash
# PiBot V3 Master Deployment Script
# Run this on the Master

set -e

echo "==============================================="
echo "PiBot V3 Master Deployment"
echo "==============================================="
echo ""

INSTALL_DIR="$HOME/pibot"
# Default worker IP if not set
WORKER_IP="${WORKER_1_IP:-127.0.0.1}"

echo "Installing to: $INSTALL_DIR"
echo "Worker IP: $WORKER_IP"
echo ""

# Create directory
cd "$INSTALL_DIR"

echo "[1/4] Installing dependencies..."
pip3 install flask aiohttp openai 2>/dev/null || echo "Dependencies may already be installed"

echo ""
echo "[2/4] Setting up environment..."

# Create/update .env file
if [ ! -f .env ]; then
    cat > .env << EOF
# PiBot V3 Master Configuration
VOLC_API_KEY=your_volc_api_key_here
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=doubao-seed-code

# Worker Configuration (single worker)
WORKER_1_IP=$WORKER_IP
# WORKER_2_IP=...  # Optional
# WORKER_3_IP=...  # Optional
EOF
    echo "Created .env file - Please edit with your actual API key!"
else
    # Update existing .env to add worker config
    if ! grep -q "WORKER_1_IP" .env; then
        echo "" >> .env
        echo "# Worker Configuration" >> .env
        echo "WORKER_1_IP=$WORKER_IP" >> .env
        echo "Updated .env with worker configuration"
    fi
fi

# Ensure environment variables are loaded
export \$(grep -v '^#' .env | xargs) 2>/dev/null || true

echo ""
echo "[3/4] Creating startup scripts..."

# Update existing start script or create new one
cat > start_master_with_worker.sh << EOF
#!/bin/bash
cd "\$(dirname "\$0")"

# Load environment variables
export \$(grep -v '^#' .env | xargs)

echo "Starting PiBot V3 Master with Worker support..."
echo "Worker: \$WORKER_1_IP"
echo ""

# Start Master
python3 master_hub.py
EOF
chmod +x start_master_with_worker.sh

echo ""
echo "[4/4] Testing Worker connectivity..."

# Test if worker is reachable
if curl -s http://\$WORKER_1_IP:5000/health > /dev/null 2>&1; then
    echo "✓ Worker is online and responding!"
    curl -s http://\$WORKER_1_IP:5000/health | python3 -m json.tool 2>/dev/null || curl -s http://\$WORKER_1_IP:5000/health
else
    echo "⚠ Worker not responding at \$WORKER_1_IP:5000"
    echo "  Make sure the worker is running before using the system"
fi

echo ""
echo "==============================================="
echo "Deployment Complete!"
echo "==============================================="
echo ""
echo "Next steps:"
echo "1. Ensure .env file has correct VOLC_API_KEY"
echo "2. Make sure worker is running on \$WORKER_1_IP:5000"
echo "3. Start Master: ./start_master_with_worker.sh"
echo ""
echo "To test the integration:"
echo "   python3 test_integration.py"
echo ""
