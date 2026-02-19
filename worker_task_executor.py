"""
PiBot V3 - Worker Task Executor

Runs on Worker nodes to:
1. Receive tasks from Master
2. Load specified skills
3. Execute tasks using Agent Core
4. Return results to Master

After task completion, worker memory is cleared (temporary agent).
"""

import os
import json
import asyncio
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

# Flask imports (wrapped in try/except for graceful degradation)
try:
    from flask import Flask, request, jsonify

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None
    request = None
    jsonify = lambda x: x  # dummy

from agent_core import (
    AgentCore,
    AgentContext,
    AgentRole,
    AgentEventStream,
    create_user_message,
    AgentMessage,
)
from llm_client import create_llm_client_from_env, LLMClient
from tool_registry import get_tool_registry

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A task being executed."""

    task_id: str
    description: str
    skills: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    agent_context: Optional[AgentContext] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
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
    """
    Worker Task Executor.

    Manages task execution on Worker nodes.
    Each task gets a fresh Agent Core instance (no persistent memory).
    """

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
        self._running = False

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load worker system prompt."""
        soul_path = Path("worker_soul.md")
        if soul_path.exists():
            return soul_path.read_text(encoding="utf-8")

        # Default system prompt
        return """You are a Worker agent in the PiBot V3 system.

Your role is to execute tasks assigned by the Master agent.

Guidelines:
1. Execute the task efficiently and accurately
2. Use the provided tools/skills to complete the task
3. Return structured results in JSON format
4. Report any errors clearly
5. Do not ask for clarification - do your best with available information

You have no persistent memory - each task is independent."""

    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task using Agent Core."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().timestamp()
        self._current_task = task

        try:
            # Create tool registry and load required skills
            registry = get_tool_registry()
            registry.clear()  # Start fresh for each task

            if task.skills:
                registry.load_skills_from_directory(self.skills_dir)
                # Filter to only requested skills
                requested_skills = set(task.skills)
                for tool_name in list(registry.list_tools()):
                    if tool_name not in requested_skills:
                        registry.unregister(tool_name)

            # Create agent context
            context = AgentContext(
                system_prompt=self.system_prompt,
                messages=[],
                tools=registry.get_all_tools(),
                role=AgentRole.WORKER,
            )

            # Create agent core
            agent = AgentCoreWithLLM(context=context, llm_client=self.llm_client)

            # Create event stream
            stream = AgentEventStream()

            # Create user message from task description
            prompt = create_user_message(task.description)

            # Execute
            logger.info(f"Starting task execution: {task.task_id}")
            messages = await agent.run([prompt], stream)

            # Extract result from messages
            result_text = self._extract_result(messages)

            task.status = TaskStatus.COMPLETED
            task.result = {"output": result_text, "message_count": len(messages)}
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
            # Clear memory
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

    def _cleanup(self):
        """Clean up after task execution."""
        # Reset tool registry
        registry = get_tool_registry()
        registry.clear()

        # Force garbage collection
        import gc

        gc.collect()

        logger.info("Worker memory cleaned up")

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def cancel_current_task(self) -> bool:
        """Cancel the currently running task."""
        if self._current_task:
            self._current_task.status = TaskStatus.CANCELLED
            self._current_task.error = "Cancelled by request"
            self._current_task.completed_at = datetime.now().timestamp()
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get worker status."""
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
        """Call LLM via the client."""
        return await self.llm_client.chat_completion(
            messages=messages, tools=tools if tools else None
        )


# ============================================================================
# Flask App (for HTTP interface)
# ============================================================================


def create_app(executor: WorkerExecutor = None) -> Optional["Flask"]:
    """Create Flask app for Worker."""
    if not FLASK_AVAILABLE:
        logger.error("Flask not available, cannot create HTTP interface")
        return None

    if executor is None:
        executor = WorkerExecutor()

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
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
        """Receive a new task from Master."""
        try:
            data = request.get_json()

            task = Task(
                task_id=data.get("task_id"),
                description=data.get("description"),
                skills=data.get("skills", []),
            )

            # Store task
            executor._tasks[task.task_id] = task

            # Start execution in background using thread
            import threading

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
        """Get worker status."""
        return jsonify(executor.get_status())

    return app


# ============================================================================
# Main Entry Point
# ============================================================================


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

    # Create executor
    executor = WorkerExecutor(
        worker_id=args.worker_id, skills_dir=Path(args.skills_dir)
    )

    # Create and run Flask app
    app = create_app(executor)

    if app:
        logger.info(f"Starting Worker on {args.host}:{args.port}")
        app.run(host=args.host, port=args.port, threaded=True)
    else:
        logger.error("Failed to create Flask app")


if __name__ == "__main__":
    main()
