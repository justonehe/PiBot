#!/bin/bash
# run_master.sh
# 强力启动脚本，解决 SSH nohup 退出问题
cd /home/justone

# 1. 杀掉旧进程
pkill -f master_hub.py || true
sleep 1

# 2. 启动新进程
# 使用 setsid 确保脱离终端
setsid python3 master_hub.py > master.log 2>&1 < /dev/null &

# 3. 检查
sleep 2
if pgrep -f "python3 master_hub.py" > /dev/null; then
    echo "SUCCESS: Master Hub is running."
    ps aux | grep master_hub
else
    echo "ERROR: Master Hub failed to start."
    cat master.log
fi
