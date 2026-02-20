"""
PiBot V3 - Worker Task Executor (Clean HTTP API Version)

接收 Master 的 HTTP POST 请求执行任务
"""

import os
import json
import asyncio
import logging
import threading
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ[key] = value

# Flask imports
try:
    from flask import Flask, request, jsonify

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None
    request = None
    jsonify = lambda x: x

from agent_core import (
    AgentCore,
    AgentContext,
    AgentRole,
    AgentEventStream,
    create_user_message,
)
from llm_client import create_llm_client_from_env, LLMClient
from tool_registry import get_tool_registry

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str
    description: str
    skills: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "skills": self.skills,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class WorkerExecutor:
    """Worker Task Executor - 使用 Agent Core 执行任务"""

    def __init__(
        self,
        worker_id: str = None,
        skills_dir: Path = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.worker_id = worker_id or f"worker_{os.environ.get('HOSTNAME', 'unknown')}"
        self.skills_dir = skills_dir or Path("skills")
        self.llm_client = llm_client or create_llm_client_from_env()

        self._tasks: Dict[str, Task] = {}
        self._current_task: Optional[Task] = None

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load worker system prompt."""
        soul_path = Path("worker_soul.md")
        if soul_path.exists():
            return soul_path.read_text(encoding="utf-8")

        return """You are a Worker agent in the PiBot V3 system.
Your role is to execute tasks assigned by the Master agent.
Guidelines:
1. Execute the task efficiently and accurately
2. Use the provided tools/skills to complete the task
3. Return structured results in JSON format
4. Report any errors clearly
You have no persistent memory - each task is independent."""

    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task using Agent Core."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().timestamp()
        self._current_task = task

        try:
            # Create tool registry and load skills
            registry = get_tool_registry()
            registry.clear()

            # Load all skills from directory
            registry.load_skills_from_directory(self.skills_dir)

            # Direct skill execution based on task description
            logger.info(f"Starting task execution: {task.task_id}")

            # Parse task to determine which skill to call
            result_text = await self._execute_skills_directly(task, registry)

            task.status = TaskStatus.COMPLETED
            task.result = {"output": result_text, "message_count": 1}
            task.completed_at = datetime.now().timestamp()

            logger.info(f"Task completed: {task.task_id}")
            return task.to_dict()

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now().timestamp()
            return task.to_dict()

        finally:
            self._current_task = None
            self._cleanup()

    def _extract_result(self, messages: list) -> str:
        """Extract final result from agent messages."""
        result_parts = []
        for msg in messages:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type.value == "text" and content.text:
                        result_parts.append(content.text)
        return "\n".join(result_parts) if result_parts else "Task completed"

    async def _execute_skills_directly(self, task: Task, registry) -> str:
        """Directly execute skills based on task description without LLM."""
        import re

        description = task.description.lower()

        # Check for coral_vision skill request
        if (
            "coral_vision" in description
            or "analyze" in description
            or "图像" in description
        ):
            # Extract image path from description
            path_match = re.search(r"/[\w/]+\.(jpg|jpeg|png)", task.description)
            if path_match:
                image_path = path_match.group(0)
            else:
                image_path = "/home/justone/tasks/photo_to_analyze.jpg"

            # Get coral_vision tool
            tool = registry.get("coral_vision")
            if tool:
                try:
                    result = await tool.execute(
                        "call_001", {"args": f"{image_path}||analyze_color"}
                    )
                    # Handle ToolResult object
                    if hasattr(result, "is_error"):
                        # It's a ToolResult
                        if result.is_error:
                            error_msg = (
                                str(result.content)
                                if result.content
                                else "Unknown error"
                            )
                            return f"图像分析失败: {error_msg}"
                        else:
                            # Extract text from content
                            texts = []
                            for c in result.content:
                                if hasattr(c, "text"):
                                    texts.append(c.text)
                            result_text = "\n".join(texts) if texts else "分析完成"
                            return f"图像分析完成:\n{result_text}"
                    else:
                        # It's a dict or other type
                        return f"分析结果: {str(result)}"
                except Exception as e:
                    return f"执行 coral_vision 时出错: {str(e)}"
            else:
                return "coral_vision 工具未加载"

        # Default: use LLM for text-based tasks
        context = AgentContext(
            system_prompt=self.system_prompt,
            messages=[],
            tools=[],
            role=AgentRole.WORKER,
        )
        agent = AgentCoreWithLLM(context=context, llm_client=self.llm_client)
        stream = AgentEventStream()
        prompt = create_user_message(task.description)
        messages = await agent.run([prompt], stream)
        return self._extract_result(messages)

    def _cleanup(self):
        """Clean up after task execution."""
        registry = get_tool_registry()
        registry.clear()
        import gc

        gc.collect()
        logger.info("Worker memory cleaned up")

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def cancel_current_task(self) -> bool:
        if self._current_task:
            self._current_task.status = TaskStatus.CANCELLED
            self._current_task.error = "Cancelled by request"
            self._current_task.completed_at = datetime.now().timestamp()
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": "busy" if self._current_task else "idle",
            "current_task": self._current_task.task_id if self._current_task else None,
            "total_tasks": len(self._tasks),
        }


class AgentCoreWithLLM(AgentCore):
    """Agent Core with integrated LLM client."""

    def __init__(self, context, llm_client, **kwargs):
        super().__init__(context, llm_client, **kwargs)
        self.llm_client = llm_client

    async def _call_llm(self, messages, tools):
        return await self.llm_client.chat_completion(
            messages=messages, tools=tools if tools else None
        )


def create_app(executor: WorkerExecutor = None) -> Optional["Flask"]:
    """Create Flask app for Worker HTTP API."""
    if not FLASK_AVAILABLE:
        logger.error("Flask not available")
        return None

    if executor is None:
        executor = WorkerExecutor()

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(
            {
                "status": "healthy",
                "worker_id": executor.worker_id,
                "current_task": executor._current_task.task_id
                if executor._current_task
                else None,
            }
        )

    @app.route("/task", methods=["POST"])
    def receive_task():
        """Receive a new task from Master via HTTP POST."""
        # Check if worker is busy
        if executor._current_task is not None:
            return jsonify(
                {"success": False, "error": "Worker busy", "status": "busy"}
            ), 409

        try:
            data = request.get_json()

            task = Task(
                task_id=data.get("task_id"),
                description=data.get("description"),
                skills=data.get("skills", []),
            )

            # Store task
            executor._tasks[task.task_id] = task

            # Execute in background thread
            def run_task():
                asyncio.run(executor.execute_task(task))

            threading.Thread(target=run_task, daemon=True).start()

            return jsonify(
                {"success": True, "task_id": task.task_id, "status": "accepted"}
            ), 202

        except Exception as e:
            logger.error(f"Failed to receive task: {e}")
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/task/<task_id>/result", methods=["GET"])
    def get_task_result(task_id: str):
        """Get task result."""
        task = executor.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404
        return jsonify(task.to_dict())

    @app.route("/task/<task_id>/cancel", methods=["POST"])
    def cancel_task(task_id: str):
        """Cancel a task."""
        if executor._current_task and executor._current_task.task_id == task_id:
            executor.cancel_current_task()
            return jsonify({"success": True, "cancelled": True})
        return jsonify(
            {"success": False, "error": "Task not running or not found"}
        ), 404

    @app.route("/status", methods=["GET"])
    def get_status():
        return jsonify(executor.get_status())

    return app


def check_and_free_port(port: int):
    """Check if port is in use and kill the process using it."""
    import subprocess
    import time
    import os

    try:
        # Try using fuser to kill processes using the port
        result = subprocess.run(
            ["fuser", "-k", f"{port}/tcp"], capture_output=True, text=True
        )
        if result.returncode == 0:
            logger.info(f"Killed processes using port {port}")
            time.sleep(1)
        else:
            # Alternative: try using ss to find and kill
            try:
                # Get PIDs using the port
                ss_result = subprocess.run(
                    ["ss", "-tlnp", f"sport = :{port}"], capture_output=True, text=True
                )
                if ss_result.returncode == 0 and "users:" in ss_result.stdout:
                    # Parse output to extract PIDs
                    import re

                    pids = re.findall(r"pid=(\d+)", ss_result.stdout)
                    for pid in pids:
                        if pid and pid != str(os.getpid()):
                            logger.warning(f"Killing PID {pid} using port {port}")
                            subprocess.run(["kill", "-9", pid], capture_output=True)
                    if pids:
                        logger.info(f"Port {port} has been freed")
                        time.sleep(1)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not check/free port {port}: {e}")


def main():
    """Main entry point for Worker."""
    import argparse

    parser = argparse.ArgumentParser(description="PiBot V3 Worker")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind")
    parser.add_argument("--skills-dir", default="skills", help="Skills directory")
    parser.add_argument("--worker-id", default=None, help="Worker ID")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Get worker_id from env var, arg, or hostname
    worker_id = os.environ.get("WORKER_ID") or args.worker_id
    if not worker_id:
        # Generate from hostname
        hostname = os.environ.get("HOSTNAME", "unknown")
        worker_id = f"worker_{hostname}"

    # Check and free port before starting
    check_and_free_port(args.port)

    # Create executor
    executor = WorkerExecutor(worker_id=worker_id, skills_dir=Path(args.skills_dir))

    # Create and run Flask app
    app = create_app(executor)

    if app:
        logger.info(f"Starting Worker {worker_id} on {args.host}:{args.port}")
        app.run(host=args.host, port=args.port, threaded=True)
    else:
        logger.error("Failed to create Flask app")


if __name__ == "__main__":
    main()
