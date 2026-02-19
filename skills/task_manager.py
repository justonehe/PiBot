"""
Task Manager Skill for PiBot Master
管理 Worker 状态和任务分配
"""

import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Worker 配置
WORKERS = {
    "worker_1": {"ip": "192.168.10.66", "name": "Worker-1", "type": "file_io"},
    "worker_2": {"ip": "192.168.10.67", "name": "Worker-2", "type": "network"},
    "worker_3": {"ip": "192.168.10.68", "name": "Worker-3", "type": "compute"},
}

# 任务状态存储
TASKS_DIR = Path("tasks")
TASKS_DIR.mkdir(exist_ok=True)


def execute(args: Optional[str] = None) -> Dict[str, Any]:
    """
    Task Manager 技能入口

    操作:
    - get_worker_status: 获取 Worker 状态
    - dispatch_task: 分派任务
    - check_task_status: 检查任务状态
    - get_all_tasks: 获取所有任务

    用法: task_manager:action||params
    """
    try:
        if not args:
            return {
                "success": False,
                "error": "Missing action",
                "message": "格式: task_manager:action||params",
                "available_actions": [
                    "get_worker_status",
                    "dispatch_task",
                    "check_task_status",
                    "get_all_tasks",
                    "cancel_task",
                ],
            }

        # 解析参数
        parts = [p.strip() for p in args.split("||")]
        action = parts[0].lower()

        if action == "get_worker_status":
            return get_worker_status()

        elif action == "dispatch_task":
            if len(parts) < 3:
                return {
                    "success": False,
                    "error": "Missing parameters",
                    "message": "格式: task_manager:dispatch_task||worker_id||task_objective",
                }
            return dispatch_task(parts[1], parts[2], parts[3] if len(parts) > 3 else "")

        elif action == "check_task_status":
            if len(parts) < 2:
                return {
                    "success": False,
                    "error": "Missing task_id",
                    "message": "格式: task_manager:check_task_status||task_id",
                }
            return check_task_status(parts[1])

        elif action == "get_all_tasks":
            return get_all_tasks()

        elif action == "cancel_task":
            if len(parts) < 2:
                return {
                    "success": False,
                    "error": "Missing task_id",
                    "message": "格式: task_manager:cancel_task||task_id",
                }
            return cancel_task(parts[1])

        else:
            return {
                "success": False,
                "error": f"Unknown action: {action}",
                "message": "可用操作: get_worker_status, dispatch_task, check_task_status, get_all_tasks, cancel_task",
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Task manager error: {str(e)}",
        }


def get_worker_status() -> Dict[str, Any]:
    """
    获取所有 Worker 的状态

    通过 ping 检查 Worker 是否在线，通过任务文件检查是否忙碌
    """
    statuses = {}

    for worker_id, config in WORKERS.items():
        # 检查是否在线
        is_online = _ping_worker(config["ip"])

        # 检查是否有活跃任务
        active_tasks = _get_worker_active_tasks(worker_id)
        is_busy = len(active_tasks) > 0

        if not is_online:
            status = "offline"
            status_text = "离线"
        elif is_busy:
            status = "busy"
            status_text = "工作中"
        else:
            status = "idle"
            status_text = "闲置"

        statuses[worker_id] = {
            "id": worker_id,
            "name": config["name"],
            "ip": config["ip"],
            "type": config["type"],
            "status": status,
            "status_text": status_text,
            "online": is_online,
            "busy": is_busy,
            "active_tasks": active_tasks,
        }

    # 统计
    idle_count = sum(1 for s in statuses.values() if s["status"] == "idle")
    busy_count = sum(1 for s in statuses.values() if s["status"] == "busy")
    offline_count = sum(1 for s in statuses.values() if s["status"] == "offline")

    return {
        "success": True,
        "message": f"Worker 状态: {idle_count} 闲置, {busy_count} 工作中, {offline_count} 离线",
        "data": {
            "workers": list(statuses.values()),
            "summary": {
                "total": len(WORKERS),
                "idle": idle_count,
                "busy": busy_count,
                "offline": offline_count,
            },
        },
    }


def dispatch_task(worker_id: str, objective: str, context: str = "") -> Dict[str, Any]:
    """
    分派任务给 Worker

    Args:
        worker_id: Worker ID (worker_1, worker_2, worker_3)
        objective: 任务目标
        context: 任务上下文

    Returns:
        Dict: 包含 task_id 和状态
    """
    if worker_id not in WORKERS:
        return {
            "success": False,
            "error": f"Unknown worker: {worker_id}",
            "message": f"可用 Worker: {', '.join(WORKERS.keys())}",
        }

    # 检查 Worker 是否在线
    config = WORKERS[worker_id]
    if not _ping_worker(config["ip"]):
        return {
            "success": False,
            "error": f"Worker {worker_id} is offline",
            "message": f"Worker {config['name']} ({config['ip']}) 当前离线，无法分派任务",
        }

    # 生成任务 ID
    task_id = f"task_{int(time.time() * 1000)}"

    # 创建任务定义
    task = {
        "task_id": task_id,
        "created_at": datetime.now().isoformat(),
        "worker_id": worker_id,
        "objective": objective,
        "context": context,
        "status": "pending",
        "type": _determine_task_type(objective),
        "skills_required": _determine_required_skills(objective),
        "ttl": 300,  # 5分钟超时
        "retry_count": 0,
        "max_retries": 2,
    }

    # 保存任务文件
    task_file = TASKS_DIR / f"{task_id}.json"
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    # 尝试分发到 Worker
    try:
        # 使用 SSH 启动 Worker 执行器
        worker_ip = config["ip"]
        remote_task_path = f"/tmp/{task_id}.json"

        # 复制任务文件到 Worker
        scp_result = subprocess.run(
            [
                "scp",
                "-o",
                "StrictHostKeyChecking=no",
                str(task_file),
                f"justone@{worker_ip}:{remote_task_path}",
            ],
            capture_output=True,
            timeout=10,
        )

        if scp_result.returncode != 0:
            # 复制失败，标记为本地执行
            task["status"] = "local_pending"
            task["error"] = f"Failed to copy to worker: {scp_result.stderr.decode()}"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)

            return {
                "success": True,  # 任务已创建，但本地执行
                "message": f"任务 {task_id} 已创建，将在本地执行（Worker 传输失败）",
                "data": {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "status": "local_pending",
                    "objective": objective,
                },
            }

        # 远程执行 Worker
        ssh_result = subprocess.run(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                f"justone@{worker_ip}",
                f"cd ~ && python3 worker_executor.py {remote_task_path} &",
            ],
            capture_output=True,
            timeout=10,
        )

        # 更新任务状态为运行中
        task["status"] = "running"
        task["started_at"] = datetime.now().isoformat()
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "message": f"任务已分派给 {config['name']}",
            "data": {
                "task_id": task_id,
                "worker_id": worker_id,
                "worker_name": config["name"],
                "status": "running",
                "objective": objective,
                "estimated_duration": "1-5 分钟",
            },
        }

    except Exception as e:
        # 执行失败，更新任务状态
        task["status"] = "failed"
        task["error"] = str(e)
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        return {"success": False, "error": str(e), "message": f"分派任务失败: {str(e)}"}


def check_task_status(task_id: str) -> Dict[str, Any]:
    """
    检查任务执行状态
    """
    task_file = TASKS_DIR / f"{task_id}.json"
    result_file = Path("outbox") / f"result_{task_id}.json"

    if not task_file.exists():
        return {
            "success": False,
            "error": "Task not found",
            "message": f"找不到任务 {task_id}",
        }

    # 加载任务定义
    with open(task_file, "r", encoding="utf-8") as f:
        task = json.load(f)

    # 检查是否有结果文件
    if result_file.exists():
        with open(result_file, "r", encoding="utf-8") as f:
            result = json.load(f)

        return {
            "success": True,
            "message": f"任务 {task_id} 已完成",
            "data": {
                "task_id": task_id,
                "status": result.get("status", "unknown"),
                "result": result.get("result", ""),
                "details": result.get("details", ""),
                "duration": result.get("duration", 0),
                "completed_at": result.get("completed_at", ""),
                "worker_id": task.get("worker_id"),
            },
        }

    # 任务仍在执行中
    created_at = datetime.fromisoformat(
        task.get("created_at", datetime.now().isoformat())
    )
    elapsed = (datetime.now() - created_at).total_seconds()

    return {
        "success": True,
        "message": f"任务 {task_id} 执行中，已耗时 {int(elapsed)} 秒",
        "data": {
            "task_id": task_id,
            "status": task.get("status", "unknown"),
            "worker_id": task.get("worker_id"),
            "objective": task.get("objective", ""),
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": task.get("ttl", 300),
        },
    }


def get_all_tasks() -> Dict[str, Any]:
    """
    获取所有任务列表
    """
    tasks = []

    for task_file in TASKS_DIR.glob("task_*.json"):
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)

            # 简化信息
            tasks.append(
                {
                    "task_id": task.get("task_id"),
                    "status": task.get("status"),
                    "worker_id": task.get("worker_id"),
                    "objective": task.get("objective", "")[:50] + "...",
                    "created_at": task.get("created_at"),
                }
            )
        except:
            continue

    # 按创建时间排序
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "success": True,
        "message": f"共 {len(tasks)} 个任务",
        "data": {
            "tasks": tasks[:20],  # 只返回最近20个
            "total": len(tasks),
        },
    }


def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    取消任务
    """
    task_file = TASKS_DIR / f"{task_id}.json"

    if not task_file.exists():
        return {
            "success": False,
            "error": "Task not found",
            "message": f"找不到任务 {task_id}",
        }

    # 加载并更新状态
    with open(task_file, "r", encoding="utf-8") as f:
        task = json.load(f)

    if task.get("status") in ["completed", "failed"]:
        return {
            "success": False,
            "error": "Task already finished",
            "message": f"任务 {task_id} 已完成，无法取消",
        }

    task["status"] = "cancelled"
    task["cancelled_at"] = datetime.now().isoformat()

    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": f"任务 {task_id} 已取消",
        "data": {"task_id": task_id, "status": "cancelled"},
    }


# 辅助函数


def _ping_worker(ip: str) -> bool:
    """Ping Worker 检查是否在线"""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False


def _get_worker_active_tasks(worker_id: str) -> List[str]:
    """获取 Worker 的活跃任务"""
    active_tasks = []

    for task_file in TASKS_DIR.glob("task_*.json"):
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)

            if task.get("worker_id") == worker_id and task.get("status") in [
                "pending",
                "running",
            ]:
                active_tasks.append(task.get("task_id"))
        except:
            continue

    return active_tasks


def _determine_task_type(objective: str) -> str:
    """根据目标确定任务类型"""
    objective_lower = objective.lower()

    if any(kw in objective_lower for kw in ["下载", "fetch", "http", "url", "网页"]):
        return "web_fetch"
    elif any(
        kw in objective_lower
        for kw in ["文件", "移动", "复制", "删除", "file", "move", "copy", "delete"]
    ):
        return "file_op"
    elif any(
        kw in objective_lower
        for kw in ["执行", "运行", "shell", "command", "cmd", "exec"]
    ):
        return "shell"
    elif any(kw in objective_lower for kw in ["skill", "技能"]):
        return "skill"
    else:
        return "generic"


def _determine_required_skills(objective: str) -> List[str]:
    """确定任务需要的技能"""
    task_type = _determine_task_type(objective)

    skill_map = {
        "web_fetch": ["web_fetch", "file_write"],
        "file_op": ["read_file", "write_file", "run_cmd"],
        "shell": ["run_cmd"],
        "skill": ["skill_manager"],
        "generic": ["read_file", "write_file"],
    }

    return skill_map.get(task_type, ["read_file", "write_file"])


def register_skills(skill_manager):
    """
    注册技能

    此技能由 Master 使用，用于管理 Worker 和任务
    """
    skill_manager.register(
        "task_manager",
        "任务管理器：查看 Worker 状态、分派任务、检查任务进度。用法: task_manager:action||params",
        execute,
    )
