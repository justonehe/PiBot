#!/bin/bash
# Stop old process
pkill -f worker_watcher.py || true
sleep 2

# Start new process in background
nohup python3 /home/justone/worker_watcher.py > /home/justone/worker.log 2>&1 &

echo "✅ Worker Watcher Started! PID: $!"
