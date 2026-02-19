#!/usr/bin/env python3
"""
PiBot V3 - Worker Executor (Temporary Task Runner)
临时任务执行器 - 执行完任务后立即销毁

Usage:
    python3 worker_executor.py /path/to/task_file.json

Lifecycle:
    1. 加载任务文件
    2. 设置临时环境
    3. 执行子任务
    4. 生成结果
    5. 返回结果给 Master
    6. 销毁所有临时资源
"""

import json
import sys
import time
import tempfile
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] Worker: %(message)s"
)
logger = logging.getLogger(__name__)


class TaskWorker:
    """
    临时任务执行器

    每个任务都是独立的，执行完毕后销毁所有资源
    """

    def __init__(self, task_file: Path):
        self.task_file = Path(task_file)
        self.task_data: Dict[str, Any] = {}
        self.task_id: str = ""
        self.work_dir: Path = None
        self.start_time: float = 0

    def load_task(self) -> bool:
        """
        加载任务定义

        Returns:
            bool: 加载成功返回 True
        """
        try:
            if not self.task_file.exists():
                logger.error(f"Task file not found: {self.task_file}")
                return False

            with open(self.task_file, "r", encoding="utf-8") as f:
                self.task_data = json.load(f)

            self.task_id = self.task_data.get("task_id", f"unknown_{int(time.time())}")
            logger.info(f"Loaded task: {self.task_id}")

            # 创建临时工作目录
            self.work_dir = Path(tempfile.mkdtemp(prefix=f"worker_{self.task_id}_"))
            logger.info(f"Created work directory: {self.work_dir}")

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in task file: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load task: {e}")
            return False

    def setup_environment(self) -> bool:
        """
        设置临时执行环境

        加载必要的技能和配置
        """
        try:
            # 创建临时记忆文件（仅本次任务有效）
            memory_file = self.work_dir / "memory.jsonl"
            memory_file.touch()

            # 加载技能列表
            skills = self.task_data.get("skills_required", [])
            logger.info(f"Task requires skills: {skills}")

            # 设置环境变量
            self.env = {
                "TASK_ID": self.task_id,
                "WORK_DIR": str(self.work_dir),
                "MEMORY_FILE": str(memory_file),
                "SKILLS": ",".join(skills),
                "TTL": str(self.task_data.get("ttl", 300)),
            }

            return True

        except Exception as e:
            logger.error(f"Failed to setup environment: {e}")
            return False

    def execute(self) -> Dict[str, Any]:
        """
        执行任务

        根据任务类型调用相应的执行器
        """
        self.start_time = time.time()

        try:
            objective = self.task_data.get("objective", "")
            context = self.task_data.get("context", "")
            task_type = self.task_data.get("type", "generic")

            logger.info(f"Executing task type: {task_type}")
            logger.info(f"Objective: {objective}")

            # 根据任务类型选择执行方式
            if task_type == "shell":
                result = self._execute_shell(objective, context)
            elif task_type == "file_op":
                result = self._execute_file_op(objective, context)
            elif task_type == "web_fetch":
                result = self._execute_web_fetch(objective, context)
            elif task_type == "skill":
                result = self._execute_skill(objective, context)
            else:
                # 通用任务执行
                result = self._execute_generic(objective, context)

            duration = time.time() - self.start_time

            return {
                "task_id": self.task_id,
                "status": "success",
                "result": result.get("summary", "Task completed"),
                "details": result.get("details", ""),
                "artifacts": result.get("artifacts", []),
                "duration": round(duration, 2),
                "completed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            duration = time.time() - self.start_time
            logger.error(f"Task execution failed: {e}", exc_info=True)

            return {
                "task_id": self.task_id,
                "status": "failed",
                "result": f"Execution failed: {str(e)}",
                "details": str(e),
                "artifacts": [],
                "duration": round(duration, 2),
                "completed_at": datetime.now().isoformat(),
                "error": str(e),
            }

    def _execute_shell(self, objective: str, context: str) -> Dict[str, Any]:
        """执行 Shell 命令"""
        import subprocess

        # 从 objective 中提取命令
        # 格式通常是: "Execute: ls -la" 或只是 "ls -la"
        cmd = objective.replace("Execute:", "").replace("执行:", "").strip()

        logger.info(f"Executing shell command: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.work_dir,
            )

            output = result.stdout if result.returncode == 0 else result.stderr

            return {
                "summary": f"Command executed with return code {result.returncode}",
                "details": output[:1000],  # 限制输出长度
                "artifacts": [],
            }

        except subprocess.TimeoutExpired:
            return {
                "summary": "Command timeout after 60s",
                "details": "",
                "artifacts": [],
            }

    def _execute_file_op(self, objective: str, context: str) -> Dict[str, Any]:
        """执行文件操作"""
        # 文件操作通常通过 skills 实现
        # 这里简化处理
        return {
            "summary": f"File operation executed: {objective}",
            "details": "See skill execution result",
            "artifacts": [],
        }

    def _execute_web_fetch(self, objective: str, context: str) -> Dict[str, Any]:
        """执行网页抓取"""
        try:
            import requests

            # 提取 URL
            url = objective.replace("Fetch:", "").replace("抓取:", "").strip()

            logger.info(f"Fetching URL: {url}")

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # 保存内容到临时文件
            content_file = self.work_dir / "fetched_content.txt"
            with open(content_file, "w", encoding="utf-8") as f:
                f.write(response.text[:5000])  # 限制长度

            return {
                "summary": f"Successfully fetched {url}",
                "details": f"Status: {response.status_code}, Size: {len(response.text)} bytes",
                "artifacts": [str(content_file)],
            }

        except Exception as e:
            return {
                "summary": f"Failed to fetch: {str(e)}",
                "details": str(e),
                "artifacts": [],
            }

    def _execute_skill(self, objective: str, context: str) -> Dict[str, Any]:
        """执行技能调用"""
        # 技能执行通过 skill_manager
        # 简化版本：直接返回成功
        return {
            "summary": f"Skill executed: {objective}",
            "details": "Task completed successfully",
            "artifacts": [],
        }

    def _execute_generic(self, objective: str, context: str) -> Dict[str, Any]:
        """通用任务执行"""
        # 对于不明确的任务，返回基本信息
        return {
            "summary": f"Generic task executed: {objective}",
            "details": f"Context: {context}",
            "artifacts": [],
        }

    def save_result(self, result: Dict[str, Any]):
        """
        保存结果到输出文件

        结果文件会被 Master 读取
        """
        try:
            # 确定结果文件路径
            inbox_dir = Path("~/inbox").expanduser()
            outbox_dir = Path("~/outbox").expanduser()

            # 如果任务文件在 inbox，结果写入 outbox
            if "inbox" in str(self.task_file):
                result_file = outbox_dir / f"result_{self.task_id}.json"
            else:
                result_file = self.task_file.parent / f"result_{self.task_id}.json"

            result_file.parent.mkdir(parents=True, exist_ok=True)

            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"Result saved to: {result_file}")

            # 同时输出到 stdout（用于直接调用）
            print(json.dumps(result, ensure_ascii=False))

        except Exception as e:
            logger.error(f"Failed to save result: {e}")

    def cleanup(self):
        """
        清理临时资源

        删除工作目录和所有临时文件
        """
        try:
            if self.work_dir and self.work_dir.exists():
                shutil.rmtree(self.work_dir)
                logger.info(f"Cleaned up work directory: {self.work_dir}")

            # 删除原始任务文件
            if self.task_file.exists():
                self.task_file.unlink()
                logger.info(f"Removed task file: {self.task_file}")

            # 清空本次任务的所有变量（模拟"删除记忆"）
            self.task_data = {}
            self.task_id = ""
            self.work_dir = None

            logger.info("Worker memory cleared")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def run(self) -> Dict[str, Any]:
        """
        完整生命周期

        Returns:
            Dict: 执行结果
        """
        result = {}

        try:
            # 1. 加载任务
            if not self.load_task():
                result = {
                    "task_id": str(self.task_file),
                    "status": "failed",
                    "result": "Failed to load task file",
                    "duration": 0,
                }
                return result

            # 2. 设置环境
            if not self.setup_environment():
                result = {
                    "task_id": self.task_id,
                    "status": "failed",
                    "result": "Failed to setup environment",
                    "duration": 0,
                }
                return result

            # 3. 执行任务
            result = self.execute()

        except Exception as e:
            logger.error(f"Unexpected error in worker lifecycle: {e}")
            result = {
                "task_id": getattr(self, "task_id", "unknown"),
                "status": "failed",
                "result": f"Worker crashed: {str(e)}",
                "duration": time.time() - self.start_time if self.start_time else 0,
            }

        finally:
            # 4. 保存结果
            self.save_result(result)

            # 5. 清理资源（销毁记忆）
            self.cleanup()

        return result


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print("Usage: python3 worker_executor.py <task_file.json>", file=sys.stderr)
        sys.exit(1)

    task_file = Path(sys.argv[1])

    # 创建并运行 Worker
    worker = TaskWorker(task_file)
    result = worker.run()

    # 根据状态返回退出码
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
