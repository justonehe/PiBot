import os
import time
import json
import glob
import subprocess
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("worker.log"),
        logging.StreamHandler()
    ]
)

INBOX = os.path.expanduser("~/inbox")
OUTBOX = os.path.expanduser("~/outbox")

# 确保目录存在
os.makedirs(INBOX, exist_ok=True)
os.makedirs(OUTBOX, exist_ok=True)

def execute_task(task_file):
    try:
        with open(task_file, 'r') as f:
            task = json.load(f)
        
        task_id = task.get("id", "unknown")
        cmd = task.get("cmd", "")
        
        logging.info(f"Received Task [{task_id}]: {cmd}")
        
        # 执行命令
        start_time = time.time()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        duration = time.time() - start_time
        
        output = {
            "id": task_id,
            "cmd": cmd,
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": duration,
            "worker": "192.168.10.66"
        }
        
    except Exception as e:
        logging.error(f"Failed to execute task: {e}")
        output = {
            "id": "error",
            "status": "exception",
            "error": str(e)
        }
    
    # 写入结果
    result_file = os.path.join(OUTBOX, f"{os.path.basename(task_file)}.result")
    with open(result_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    logging.info(f"Task finished. Result wrote to {result_file}")
    
    # 删除任务文件
    try:
        os.remove(task_file)
    except Exception as e:
        logging.error(f"Failed to delete task file: {e}")

def main():
    logging.info("Worker Watcher Started. Monitoring ~/inbox ...")
    while True:
        tasks = glob.glob(os.path.join(INBOX, "*.json"))
        for task_file in tasks:
            # 简单锁机制：检查文件是否写入完成 (或者依赖 mv 原子性)
            # 这里直接执行
            execute_task(task_file)
        
        time.sleep(1)

if __name__ == "__main__":
    main()
