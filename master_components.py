"""
PiBot V3 - Master Components
TaskPlanner and WorkerPool for Master Hub

Based on the architecture design from docs/ARCHITECTURE_V3_FINAL.md
"""

import os
import json
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels."""

    SIMPLE = "simple"  # Handle locally
    MODERATE = "moderate"  # Decide based on load
    COMPLEX = "complex"  # Delegate to Worker


class WorkerStatus(Enum):
    """Worker status states."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


@dataclass
class WorkerInfo:
    """Information about a worker."""

    worker_id: str
    ip: str
    port: int = 5000
    status: WorkerStatus = WorkerStatus.IDLE
    current_task: Optional[str] = None
    last_heartbeat: Optional[float] = None
    capabilities: List[str] = field(default_factory=list)

    def is_available(self) -> bool:
        """Check if worker is available for new tasks."""
        return self.status == WorkerStatus.IDLE

    def get_url(self, endpoint: str = "") -> str:
        """Get worker URL for an endpoint."""
        return f"http://{self.ip}:{self.port}{endpoint}"


@dataclass
class SubTask:
    """A subtask created by TaskPlanner."""

    task_id: str
    description: str
    worker_id: Optional[str] = None
    status: str = "pending"  # pending, assigned, completed, failed
    result: Optional[Dict[str, Any]] = None
    skills: List[str] = field(default_factory=list)


@dataclass
class TaskPlan:
    """Plan created by TaskPlanner for a complex task."""

    original_task: str
    complexity: TaskComplexity
    handle_locally: bool
    subtasks: List[SubTask] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    estimated_time: Optional[int] = None  # seconds
    reasoning: str = ""


class TaskPlanner:
    """
    Task Planner for Master Hub.

    Evaluates task complexity and decides:
    - Handle locally (simple tasks)
    - Delegate to Worker (complex tasks)
    - Split into subtasks (very complex tasks)
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    async def analyze_task(self, task_description: str) -> TaskPlan:
        """
        Analyze a task and create a plan.

        Rules (from architecture design):
        - Simple: Local file operations, simple queries, system status checks
        - Complex: Network tasks, compute-intensive work, hardware access
        - Either: Code writing (decided based on current load)
        """
        # Quick heuristic analysis
        complexity = self._heuristic_analysis(task_description)

        # If LLM client available, do deeper analysis
        if self.llm_client:
            try:
                complexity = await self._llm_analysis(task_description)
            except Exception as e:
                logger.warning(f"LLM analysis failed, using heuristic: {e}")

        # Create plan based on complexity
        return self._create_plan(task_description, complexity)

    def _heuristic_analysis(self, task: str) -> TaskComplexity:
        """Quick heuristic-based complexity analysis."""
        task_lower = task.lower()

        # Complex task indicators
        complex_indicators = [
            "download",
            "fetch",
            "scrape",
            "network",
            "web",
            "http",
            "url",
            "sensor",
            "gpio",
            "hardware",
            "camera",
            "sensor",
            "i2c",
            "spi",
            "compute",
            "calculate",
            "process",
            "analyze large",
            "batch",
            "deploy",
            "install",
            "configure system",
        ]

        # Simple task indicators
        simple_indicators = [
            "read file",
            "write file",
            "list",
            "show",
            "display",
            "get status",
            "check",
            "what is",
            "tell me",
            "simple query",
        ]

        # Check for complex indicators
        for indicator in complex_indicators:
            if indicator in task_lower:
                return TaskComplexity.COMPLEX

        # Check for simple indicators
        for indicator in simple_indicators:
            if indicator in task_lower:
                return TaskComplexity.SIMPLE

        # Default to moderate if unclear
        return TaskComplexity.MODERATE

    async def _llm_analysis(self, task: str) -> TaskComplexity:
        """Use LLM for deeper task analysis."""
        prompt = f"""Analyze this task and determine its complexity:

Task: {task}

Classify as one of:
1. SIMPLE - Can be handled locally (file operations, simple queries, status checks)
2. MODERATE - Could go either way (code writing, moderate computation)
3. COMPLEX - Should delegate to worker (network tasks, hardware access, heavy compute)

Respond with ONLY the classification word: SIMPLE, MODERATE, or COMPLEX."""

        try:
            response = await self.llm_client.chat_completion(
                [{"role": "user", "content": prompt}]
            )

            content = response.get("content", [{}])[0].get("text", "MODERATE")
            content_upper = content.upper()

            if "SIMPLE" in content_upper:
                return TaskComplexity.SIMPLE
            elif "COMPLEX" in content_upper:
                return TaskComplexity.COMPLEX
            else:
                return TaskComplexity.MODERATE

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return TaskComplexity.MODERATE

    def _create_plan(self, task: str, complexity: TaskComplexity) -> TaskPlan:
        """Create execution plan based on complexity."""

        if complexity == TaskComplexity.SIMPLE:
            return TaskPlan(
                original_task=task,
                complexity=complexity,
                handle_locally=True,
                subtasks=[],
                reasoning="Simple task - handle locally",
            )

        elif complexity == TaskComplexity.COMPLEX:
            # Split into subtasks for parallel execution
            subtasks = self._split_into_subtasks(task)

            return TaskPlan(
                original_task=task,
                complexity=complexity,
                handle_locally=False,
                subtasks=subtasks,
                required_skills=self._detect_required_skills(task),
                reasoning="Complex task - delegate to workers",
            )

        else:  # MODERATE
            # Decide based on current load (simplified: always handle locally for now)
            return TaskPlan(
                original_task=task,
                complexity=complexity,
                handle_locally=True,  # Can be changed based on load
                subtasks=[],
                reasoning="Moderate task - handle locally based on current load",
            )

    def _split_into_subtasks(self, task: str) -> List[SubTask]:
        """Split a complex task into subtasks."""
        # Simple heuristic splitting - can be enhanced with LLM
        subtasks = []

        # Check for multi-part tasks
        if "and" in task.lower() or "," in task:
            parts = [
                p.strip()
                for p in task.replace(",", " and ").split(" and ")
                if p.strip()
            ]
            for i, part in enumerate(parts, 1):
                subtasks.append(
                    SubTask(
                        task_id=f"subtask_{i}",
                        description=part,
                        skills=self._detect_required_skills(part),
                    )
                )
        else:
            # Single subtask
            subtasks.append(
                SubTask(
                    task_id="subtask_1",
                    description=task,
                    skills=self._detect_required_skills(task),
                )
            )

        return subtasks

    def _detect_required_skills(self, task: str) -> List[str]:
        """Detect required skills for a task."""
        task_lower = task.lower()
        skills = []

        # Map task keywords to skills
        skill_map = {
            "web_fetch": ["download", "fetch", "web", "http", "url", "scrape"],
            "file_ops": ["read", "write", "file", "directory"],
            "shell": ["command", "execute", "run", "shell"],
            "dashboard_update": ["dashboard", "display", "show", "update screen"],
            "weather": ["weather", "temperature", "forecast"],
            "system": ["system", "status", "health", "monitor"],
        }

        for skill, keywords in skill_map.items():
            for keyword in keywords:
                if keyword in task_lower:
                    skills.append(skill)
                    break

        return list(set(skills))  # Remove duplicates


class WorkerPool:
    """
    Worker Pool for Master Hub.

    Manages 3 Workers:
    - Monitors status (idle/busy/offline)
    - Assigns tasks to available workers
    - Collects results from workers
    """

    def __init__(self):
        self.workers: Dict[str, WorkerInfo] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    def add_worker(
        self, worker_id: str, ip: str, port: int = 5000, capabilities: List[str] = None
    ):
        """Add a worker to the pool."""
        self.workers[worker_id] = WorkerInfo(
            worker_id=worker_id, ip=ip, port=port, capabilities=capabilities or []
        )
        logger.info(f"Added worker {worker_id} at {ip}:{port}")

    def remove_worker(self, worker_id: str):
        """Remove a worker from the pool."""
        if worker_id in self.workers:
            del self.workers[worker_id]
            logger.info(f"Removed worker {worker_id}")

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get worker info by ID."""
        return self.workers.get(worker_id)

    def get_available_worker(self) -> Optional[WorkerInfo]:
        """Get an available (idle) worker."""
        for worker in self.workers.values():
            if worker.is_available():
                return worker
        return None

    def get_all_workers(self) -> List[WorkerInfo]:
        """Get all workers."""
        return list(self.workers.values())

    async def check_worker_health(self, worker_id: str) -> bool:
        """Check if a worker is healthy."""
        worker = self.workers.get(worker_id)
        if not worker:
            return False

        try:
            session = await self._get_session()
            async with session.get(worker.get_url("/health")) as response:
                if response.status == 200:
                    worker.status = (
                        WorkerStatus.IDLE
                        if not worker.current_task
                        else WorkerStatus.BUSY
                    )
                    worker.last_heartbeat = datetime.now().timestamp()
                    return True
                else:
                    worker.status = WorkerStatus.OFFLINE
                    return False
        except Exception as e:
            logger.warning(f"Health check failed for {worker_id}: {e}")
            worker.status = WorkerStatus.OFFLINE
            return False

    async def check_all_workers_health(self) -> Dict[str, bool]:
        """Check health of all workers."""
        results = {}
        for worker_id in self.workers:
            results[worker_id] = await self.check_worker_health(worker_id)
        return results

    async def assign_task(
        self, worker_id: str, task: SubTask, timeout: int = 300
    ) -> bool:
        """Assign a task to a worker."""
        worker = self.workers.get(worker_id)
        if not worker or not worker.is_available():
            logger.error(f"Worker {worker_id} not available")
            return False

        try:
            # Mark worker as busy
            worker.status = WorkerStatus.BUSY
            worker.current_task = task.task_id

            # Send task to worker
            session = await self._get_session()
            payload = {
                "task_id": task.task_id,
                "description": task.description,
                "skills": task.skills,
            }

            async with session.post(
                worker.get_url("/task"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status == 202:  # Accepted
                    data = await response.json()
                    logger.info(f"Task {task.task_id} assigned to {worker_id}")
                    return True
                else:
                    logger.error(
                        f"Failed to assign task to {worker_id}: {response.status}"
                    )
                    worker.status = WorkerStatus.IDLE
                    worker.current_task = None
                    return False

        except Exception as e:
            logger.error(f"Error assigning task to {worker_id}: {e}")
            worker.status = WorkerStatus.IDLE
            worker.current_task = None
            return False

    async def get_task_result(
        self, worker_id: str, task_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get result of a task from a worker."""
        worker = self.workers.get(worker_id)
        if not worker:
            return None

        try:
            session = await self._get_session()
            async with session.get(
                worker.get_url(f"/task/{task_id}/result")
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # Mark worker as idle if task completed
                    if data.get("status") in ["completed", "failed"]:
                        worker.status = WorkerStatus.IDLE
                        worker.current_task = None

                    return data
                else:
                    logger.warning(
                        f"Failed to get result from {worker_id}: {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error getting result from {worker_id}: {e}")
            return None

    async def execute_task(
        self, task: SubTask, worker_id: Optional[str] = None, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Execute a task on a worker and wait for result.

        If worker_id is not specified, picks an available worker.
        """
        # Find worker
        if worker_id:
            worker = self.workers.get(worker_id)
        else:
            worker = self.get_available_worker()

        if not worker:
            return {
                "success": False,
                "error": "No available workers",
                "task_id": task.task_id,
            }

        # Assign task
        if not await self.assign_task(worker.worker_id, task, timeout):
            return {
                "success": False,
                "error": f"Failed to assign task to {worker.worker_id}",
                "task_id": task.task_id,
            }

        # Poll for result
        start_time = datetime.now().timestamp()
        poll_interval = 2  # seconds

        while True:
            # Check timeout
            elapsed = datetime.now().timestamp() - start_time
            if elapsed > timeout:
                # Cancel task
                await self.cancel_task(worker.worker_id, task.task_id)
                return {
                    "success": False,
                    "error": "Task timeout",
                    "task_id": task.task_id,
                    "elapsed": elapsed,
                }

            # Get result
            result = await self.get_task_result(worker.worker_id, task.task_id)
            if result:
                status = result.get("status")
                if status == "completed":
                    return {
                        "success": True,
                        "data": result.get("result"),
                        "task_id": task.task_id,
                        "worker_id": worker.worker_id,
                        "elapsed": elapsed,
                    }
                elif status == "failed":
                    return {
                        "success": False,
                        "error": result.get("error", "Task failed"),
                        "task_id": task.task_id,
                        "worker_id": worker.worker_id,
                    }

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    async def cancel_task(self, worker_id: str, task_id: str) -> bool:
        """Cancel a running task on a worker."""
        worker = self.workers.get(worker_id)
        if not worker:
            return False

        try:
            session = await self._get_session()
            async with session.post(
                worker.get_url(f"/task/{task_id}/cancel")
            ) as response:
                if response.status == 200:
                    worker.status = WorkerStatus.IDLE
                    worker.current_task = None
                    return True
                return False
        except Exception as e:
            logger.error(f"Error canceling task: {e}")
            return False

    async def start_monitoring(self, interval: int = 30):
        """Start periodic health monitoring of all workers."""
        if self._monitoring:
            return

        self._monitoring = True

        async def monitor_loop():
            while self._monitoring:
                await self.check_all_workers_health()
                await asyncio.sleep(interval)

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info(f"Started worker monitoring (interval: {interval}s)")

    async def stop_monitoring(self):
        """Stop worker health monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped worker monitoring")

    async def close(self):
        """Close the worker pool."""
        await self.stop_monitoring()
        if self._session and not self._session.closed:
            await self._session.close()

    def get_status_summary(self) -> Dict[str, Any]:
        """Get status summary of all workers."""
        return {
            "total": len(self.workers),
            "idle": sum(
                1 for w in self.workers.values() if w.status == WorkerStatus.IDLE
            ),
            "busy": sum(
                1 for w in self.workers.values() if w.status == WorkerStatus.BUSY
            ),
            "offline": sum(
                1 for w in self.workers.values() if w.status == WorkerStatus.OFFLINE
            ),
            "workers": [
                {
                    "id": w.worker_id,
                    "ip": w.ip,
                    "status": w.status.value,
                    "current_task": w.current_task,
                }
                for w in self.workers.values()
            ],
        }


# ============================================================================
# Convenience Functions
# ============================================================================


def create_default_worker_pool() -> WorkerPool:
    """Create a worker pool with workers from environment."""
    pool = WorkerPool()

    # Add workers from environment variables (support 1-3 workers)
    workers_config = []

    # Worker 1 (primary)
    worker1_ip = os.environ.get("WORKER_1_IP", "")
    if worker1_ip and not worker1_ip.startswith("${"):
        workers_config.append(("worker-1", worker1_ip))

    # Worker 2 (optional)
    worker2_ip = os.environ.get("WORKER_2_IP", "")
    if worker2_ip:
        workers_config.append(("worker-2", worker2_ip))

    # Worker 3 (optional)
    worker3_ip = os.environ.get("WORKER_3_IP", "")
    if worker3_ip:
        workers_config.append(("worker-3", worker3_ip))

    for worker_id, ip in workers_config:
        pool.add_worker(worker_id, ip)

    return pool


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    print("Master Components module loaded")
    print("Use TaskPlanner and WorkerPool to manage tasks and workers")
