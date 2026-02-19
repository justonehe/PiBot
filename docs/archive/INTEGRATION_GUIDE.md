# PiBot V3 Master-Worker Integration Guide

## Overview

This guide walks you through deploying and testing the new Master-Worker architecture.

## Prerequisites

### Hardware
- **Master**: Raspberry Pi 4 (192.168.10.113)
- **Workers**: 3x Raspberry Pi Zero 2W (192.168.10.66, 67, 68)
- All devices on same network
- SSH access to all devices

### Software
- Python 3.9+
- pip3
- Git (optional)

## Deployment Steps

### 1. Deploy Workers (3x Raspberry Pi Zeros)

On **each Worker** (192.168.10.66, 67, 68):

```bash
# SSH into Worker
ssh pi@192.168.10.66  # Repeat for .67 and .68

# Create project directory
mkdir -p ~/pibot-worker
cd ~/pibot-worker

# Copy files from Master (or clone from git)
# Option 1: Copy via SCP
scp -r master@192.168.10.113:~/pibot/skills ./
scp master@192.168.10.113:~/pibot/agent_core.py ./
scp master@192.168.10.113:~/pibot/llm_client.py ./
scp master@192.168.10.113:~/pibot/tool_registry.py ./
scp master@192.168.10.113:~/pibot/worker_task_executor.py ./

# Option 2: Clone repository
git clone https://github.com/yourusername/pibot-v3.git
cd pibot-v3
```

Install dependencies:
```bash
# Install Python dependencies
pip3 install flask aiohttp

# Optional: Install OpenAI library for better performance
pip3 install openai
```

Create environment file:
```bash
# Create .env file
cat > .env << 'EOF'
VOLC_API_KEY=your_volc_api_key_here
VOLC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL_NAME=doubao-seed-code
WORKER_ID=worker-1  # Change to worker-2, worker-3 on other Workers
EOF
```

Create worker system prompt:
```bash
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
```

Start the Worker:
```bash
# Start Worker on port 5000
python3 worker_task_executor.py --port 5000 --worker-id worker-1

# Or run in background with nohup
nohup python3 worker_task_executor.py --port 5000 --worker-id worker-1 > worker.log 2>&1 &
```

Verify Worker is running:
```bash
# Check if service is up
curl http://192.168.10.66:5000/health

# Expected response:
# {"status": "healthy", "worker_id": "worker-1", "current_task": null}
```

**Repeat for all 3 Workers** (changing IPs and worker IDs):
- Worker-1: 192.168.10.66:5000
- Worker-2: 192.168.10.67:5000  
- Worker-3: 192.168.10.68:5000

### 2. Configure Master

On **Master** (192.168.10.113):

Update environment variables:
```bash
# Add to ~/.bashrc or create ~/.env file
export WORKER_1_IP=192.168.10.66
export WORKER_2_IP=192.168.10.67
export WORKER_3_IP=192.168.10.68
```

Copy the new soul.md:
```bash
# The new soul.md has been created
cat soul.md
```

### 3. Install Systemd Service for Workers

Create systemd service to auto-start Workers on boot:

```bash
# On each Worker
sudo tee /etc/systemd/system/pibot-worker.service << 'EOF'
[Unit]
Description=PiBot V3 Worker
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pibot-worker
Environment="VOLC_API_KEY=your_api_key"
Environment="WORKER_ID=worker-1"
ExecStart=/usr/bin/python3 worker_task_executor.py --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pibot-worker
sudo systemctl start pibot-worker

# Check status
sudo systemctl status pibot-worker
```

## Testing

### Test 1: Verify Worker Health

```bash
# Test each Worker
curl http://192.168.10.66:5000/health
curl http://192.168.10.67:5000/health
curl http://192.168.10.68:5000/health

# Expected response for each:
# {
#   "status": "healthy",
#   "worker_id": "worker-1",
#   "current_task": null
# }
```

### Test 2: Simple Task Dispatch

```bash
# Send a simple task to Worker-1
curl -X POST http://192.168.10.66:5000/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test_001",
    "description": "List files in home directory",
    "skills": ["shell_exec"]
  }'

# Expected: {"success": true, "task_id": "test_001", "status": "accepted"}

# Wait a few seconds, then get result
curl http://192.168.10.66:5000/task/test_001/result
```

### Test 3: Network Task

```bash
# Send a network task to Worker-2
curl -X POST http://192.168.10.67:5000/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test_download",
    "description": "Download https://example.com and return the title",
    "skills": ["web_fetch"]
  }'

# Check result
curl http://192.168.10.67:5000/task/test_download/result
```

### Test 4: Master Integration Test

Create a test script on Master:

```python
#!/usr/bin/env python3
# test_integration.py

import asyncio
from master_components import TaskPlanner, create_default_worker_pool
from llm_client import create_llm_client_from_env

async def test_simple_task():
    """Test simple task delegation."""
    print("=== Test 1: Simple Task Delegation ===")
    
    # Initialize
    llm_client = create_llm_client_from_env()
    planner = TaskPlanner(llm_client)
    worker_pool = create_default_worker_pool()
    
    # Test worker health
    print("Checking Worker health...")
    health = await worker_pool.check_all_workers_health()
    for worker_id, is_healthy in health.items():
        status = "✓" if is_healthy else "✗"
        print(f"  {worker_id}: {status}")
    
    # Analyze task
    print("\nAnalyzing task...")
    plan = await planner.analyze_task("List files in /home/pi")
    print(f"  Complexity: {plan.complexity.value}")
    print(f"  Handle locally: {plan.handle_locally}")
    print(f"  Subtasks: {len(plan.subtasks)}")
    
    if not plan.handle_locally and plan.subtasks:
        # Delegate to worker
        subtask = plan.subtasks[0]
        print(f"\nDelegating to Worker...")
        result = await worker_pool.execute_task(subtask)
        print(f"  Success: {result['success']}")
        print(f"  Worker: {result.get('worker_id')}")
        if result.get('data'):
            print(f"  Output: {result['data'].get('output', 'N/A')[:200]}")
    
    await worker_pool.close()
    print("\n✓ Test completed")

async def test_worker_status():
    """Test worker status monitoring."""
    print("\n=== Test 2: Worker Status ===")
    
    worker_pool = create_default_worker_pool()
    status = worker_pool.get_status_summary()
    
    print(f"Total Workers: {status['total']}")
    print(f"  Idle: {status['idle']}")
    print(f"  Busy: {status['busy']}")
    print(f"  Offline: {status['offline']}")
    
    for worker in status['workers']:
        print(f"\n  {worker['id']}:")
        print(f"    IP: {worker['ip']}")
        print(f"    Status: {worker['status']}")
        print(f"    Current Task: {worker['current_task'] or 'None'}")
    
    await worker_pool.close()
    print("\n✓ Test completed")

async def main():
    print("PiBot V3 Master-Worker Integration Tests")
    print("=" * 50)
    
    try:
        await test_worker_status()
        await test_simple_task()
        print("\n" + "=" * 50)
        print("All tests passed!")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
```

Run the test:
```bash
python3 test_integration.py
```

### Test 5: Load Test

Test parallel task execution:

```python
#!/usr/bin/env python3
# test_load.py

import asyncio
from master_components import create_default_worker_pool, SubTask

async def test_parallel_execution():
    """Test parallel task execution on multiple workers."""
    print("=== Load Test: Parallel Execution ===")
    
    worker_pool = create_default_worker_pool()
    
    # Create 3 tasks
    tasks = [
        SubTask(
            task_id=f"parallel_{i}",
            description=f"Sleep for {i+1} seconds",
            skills=["shell_exec"]
        )
        for i in range(3)
    ]
    
    # Execute all in parallel
    print("Starting 3 parallel tasks...")
    start_time = asyncio.get_event_loop().time()
    
    results = await asyncio.gather(*[
        worker_pool.execute_task(task)
        for task in tasks
    ])
    
    end_time = asyncio.get_event_loop().time()
    total_time = end_time - start_time
    
    print(f"\nResults:")
    for i, result in enumerate(results):
        print(f"  Task {i}: {'✓' if result['success'] else '✗'}")
    
    print(f"\nTotal time: {total_time:.2f}s")
    print(f"If parallel: should be ~3s")
    print(f"If serial: would be ~6s")
    
    await worker_pool.close()

if __name__ == "__main__":
    asyncio.run(test_parallel_execution())
```

## Troubleshooting

### Worker Not Responding

```bash
# Check if Flask app is running
curl http://192.168.10.66:5000/health

# Check logs
sudo journalctl -u pibot-worker -f

# Restart Worker
sudo systemctl restart pibot-worker
```

### Task Timeout

Increase timeout in Master:
```python
result = await worker_pool.execute_task(subtask, timeout=600)  # 10 minutes
```

### Worker Shows Offline

```bash
# Check network connectivity
ping 192.168.10.66

# Check firewall
sudo ufw status

# Check if port is open
nc -zv 192.168.10.66 5000
```

### Import Errors

```bash
# Install missing dependencies
pip3 install flask aiohttp openai

# Check Python version
python3 --version  # Should be 3.9+
```

## Monitoring

### View Worker Status Dashboard

Access Master's dashboard:
```
http://192.168.10.113:5000/dashboard
```

Should show:
- Worker-1 status
- Worker-2 status
- Worker-3 status
- Active tasks
- Recent activity

### Logs

Master logs:
```bash
tail -f ~/pibot/logs/master_$(date +%Y%m%d).log
```

Worker logs:
```bash
# On each Worker
tail -f ~/pibot-worker/worker.log

# Or via systemd
sudo journalctl -u pibot-worker -f
```

## Performance Tuning

### Increase Worker Timeout

Edit `master_components.py`:
```python
# In WorkerPool.execute_task()
result = await worker_pool.execute_task(subtask, timeout=600)  # 10 min
```

### Enable Keep-Alive

Workers use HTTP keep-alive by default via aiohttp session reuse.

### Optimize Skill Loading

Only load required skills per task:
```python
# Worker only loads skills specified in task
skills = ["web_fetch", "file_ops"]  # Only these loaded
```

## Production Checklist

- [ ] All 3 Workers installed and running
- [ ] Systemd services enabled
- [ ] Health checks pass
- [ ] Task dispatch works
- [ ] Results collection works
- [ ] Error handling tested
- [ ] Logs configured
- [ ] Monitoring dashboard working
- [ ] Backup strategy for Master
- [ ] Firewall rules configured
- [ ] SSL/TLS (optional, for remote access)

## Architecture Validation

Verify the architecture is working correctly:

1. **Worker Independence**
   ```bash
   # Worker 1 should not see Worker 2's files
   curl -X POST http://192.168.10.66:5000/task \
     -d '{"task_id":"test","description":"Create test file","skills":["file_ops"]}'
   
   curl http://192.168.10.67:5000/task/test/result
   # Should show file not found (different filesystem)
   ```

2. **Memory Isolation**
   ```bash
   # Run task on Worker
   curl -X POST http://192.168.10.66:5000/task \
     -d '{"task_id":"mem1","description":"Remember this: secret123","skills":[]}'
   
   # Run another task
   curl -X POST http://192.168.10.66:5000/task \
     -d '{"task_id":"mem2","description":"What did I say?","skills":[]}'
   
   # Second task should not know about "secret123"
   ```

3. **Parallel Execution**
   ```bash
   # All 3 Workers should handle tasks simultaneously
   # Total time should be ~max(task_duration), not sum
   ```

## Next Steps

1. **Integration with Master Hub**
   - Update `master_hub.py` to use new components
   - Add TaskPlanner integration
   - Add WorkerPool to Flask routes

2. **Enhanced Monitoring**
   - Add Prometheus metrics
   - Create Grafana dashboard
   - Set up alerts

3. **Security**
   - Add API key authentication
   - Enable HTTPS
   - Add request rate limiting

4. **Optimization**
   - Implement task queue
   - Add Worker auto-scaling
   - Optimize skill loading

## Support

For issues or questions:
1. Check logs: `journalctl -u pibot-worker -f`
2. Test connectivity: `curl http://WORKER_IP:5000/health`
3. Verify environment variables
4. Check Python dependencies
