"""
PiBot V3 - Tool Registry
Manages tool registration, loading, and execution

Integrates with skills system to provide tools for Agent Core
"""

import os
import json
import asyncio
import importlib.util
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
import logging

from agent_core import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing agent tools."""

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}
        self._skill_dir: Optional[Path] = None

    def register(self, tool: AgentTool):
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister(self, name: str):
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")

    def get(self, name: str) -> Optional[AgentTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_tools(self) -> List[AgentTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def clear(self):
        """Clear all registered tools."""
        self._tools.clear()

    def create_tool_from_skill(
        self, name: str, skill_module: Any, skill_meta: Dict[str, Any]
    ) -> Optional[AgentTool]:
        """Create an AgentTool from a skill module."""
        try:
            # Get the execute function
            execute_func = getattr(skill_module, "execute", None)
            if not execute_func:
                logger.error(f"Skill {name} has no execute function")
                return None

            # Build input schema from SKILL_META
            parameters = skill_meta.get("parameters", {})
            input_schema = {
                "type": "object",
                "properties": parameters,
                "required": list(parameters.keys()),
            }

            # Create async wrapper for execute function
            async def async_execute(
                tool_call_id: str, params: Dict[str, Any]
            ) -> ToolResult:
                try:
                    # Check if execute is async
                    if asyncio.iscoroutinefunction(execute_func):
                        result = await execute_func(**params)
                    else:
                        # Run sync function in executor
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, lambda: execute_func(**params)
                        )

                    # Convert result to ToolResult
                    if isinstance(result, ToolResult):
                        return result
                    elif isinstance(result, dict):
                        if result.get("success", False):
                            return ToolResult.text(
                                json.dumps(result, ensure_ascii=False), details=result
                            )
                        else:
                            return ToolResult.error(
                                result.get("error", "Unknown error"), details=result
                            )
                    else:
                        return ToolResult.text(str(result))

                except Exception as e:
                    logger.error(f"Tool {name} execution failed: {e}")
                    return ToolResult.error(str(e))

            return AgentTool(
                name=name,
                label=skill_meta.get("label", name),
                description=skill_meta.get("description", f"Execute {name}"),
                input_schema=input_schema,
                execute=async_execute,
            )

        except Exception as e:
            logger.error(f"Failed to create tool from skill {name}: {e}")
            return None

    def load_skill_from_file(self, skill_path: Path) -> Optional[AgentTool]:
        """Load a skill from a Python file."""
        try:
            if not skill_path.exists():
                logger.error(f"Skill file not found: {skill_path}")
                return None

            # Get skill name from filename
            skill_name = skill_path.stem

            # Load module
            spec = importlib.util.spec_from_file_location(skill_name, skill_path)
            if not spec or not spec.loader:
                logger.error(f"Failed to load spec for {skill_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get SKILL_META
            skill_meta = getattr(module, "SKILL_META", None)
            if not skill_meta:
                logger.warning(f"Skill {skill_name} has no SKILL_META, using defaults")
                skill_meta = {
                    "name": skill_name,
                    "label": skill_name,
                    "description": f"Execute {skill_name}",
                    "parameters": {},
                }

            return self.create_tool_from_skill(skill_name, module, skill_meta)

        except Exception as e:
            logger.error(f"Failed to load skill from {skill_path}: {e}")
            return None

    def load_skills_from_directory(self, skills_dir: Path) -> int:
        """Load all skills from a directory. Returns count of loaded skills."""
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return 0

        count = 0
        for skill_file in skills_dir.glob("*.py"):
            if skill_file.name.startswith("_"):
                continue  # Skip private modules

            tool = self.load_skill_from_file(skill_file)
            if tool:
                self.register(tool)
                count += 1

        logger.info(f"Loaded {count} skills from {skills_dir}")
        return count

    def set_skill_directory(self, skills_dir: Path):
        """Set the skills directory and load all skills."""
        self._skill_dir = skills_dir
        self.load_skills_from_directory(skills_dir)

    def reload_skill(self, skill_name: str) -> bool:
        """Reload a single skill."""
        if not self._skill_dir:
            logger.error("No skill directory set")
            return False

        skill_path = self._skill_dir / f"{skill_name}.py"
        if not skill_path.exists():
            logger.error(f"Skill file not found: {skill_path}")
            return False

        # Unregister existing
        self.unregister(skill_name)

        # Load new
        tool = self.load_skill_from_file(skill_path)
        if tool:
            self.register(tool)
            return True
        return False

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get all tools in LLM-compatible schema format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
        ]


# ============================================================================
# Built-in Tools
# ============================================================================


def create_built_in_tools() -> List[AgentTool]:
    """Create built-in tools available to all agents."""
    tools = []

    # File operations tool
    async def file_read(tool_call_id: str, params: Dict[str, Any]) -> ToolResult:
        """Read a file."""
        try:
            path = Path(params["path"])
            if not path.exists():
                return ToolResult.error(f"File not found: {path}")

            content = path.read_text(encoding="utf-8")
            return ToolResult.text(content, {"path": str(path), "size": len(content)})
        except Exception as e:
            return ToolResult.error(str(e))

    tools.append(
        AgentTool(
            name="file_read",
            label="Read File",
            description="Read contents of a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"}
                },
                "required": ["path"],
            },
            execute=file_read,
        )
    )

    # File write tool
    async def file_write(tool_call_id: str, params: Dict[str, Any]) -> ToolResult:
        """Write to a file."""
        try:
            path = Path(params["path"])
            content = params["content"]

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            path.write_text(content, encoding="utf-8")
            return ToolResult.text(
                f"File written: {path}", {"path": str(path), "size": len(content)}
            )
        except Exception as e:
            return ToolResult.error(str(e))

    tools.append(
        AgentTool(
            name="file_write",
            label="Write File",
            description="Write content to a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
            execute=file_write,
        )
    )

    # Shell command tool
    async def shell_exec(tool_call_id: str, params: Dict[str, Any]) -> ToolResult:
        """Execute a shell command."""
        try:
            import subprocess

            cmd = params["command"]
            timeout = params.get("timeout", 30)

            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            success = result.returncode == 0
            if success:
                return ToolResult.text(
                    output, {"command": cmd, "exit_code": result.returncode}
                )
            else:
                return ToolResult.error(
                    output, {"command": cmd, "exit_code": result.returncode}
                )

        except subprocess.TimeoutExpired:
            return ToolResult.error(f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult.error(str(e))

    tools.append(
        AgentTool(
            name="shell_exec",
            label="Execute Shell Command",
            description="Execute a shell command",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout": {"type": "number", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            execute=shell_exec,
        )
    )

    # Memory tool
    async def memory_read(tool_call_id: str, params: Dict[str, Any]) -> ToolResult:
        """Read from memory/tape file."""
        try:
            memory_file = Path("memory.jsonl")
            if not memory_file.exists():
                return ToolResult.text("No memory file found", {"entries": 0})

            lines = memory_file.read_text().strip().split("\n")
            entries = [json.loads(line) for line in lines if line.strip()]

            limit = params.get("limit", 10)
            entries = entries[-limit:] if limit > 0 else entries

            return ToolResult.text(
                json.dumps(entries, indent=2, ensure_ascii=False),
                {"entries": len(entries)},
            )
        except Exception as e:
            return ToolResult.error(str(e))

    tools.append(
        AgentTool(
            name="memory_read",
            label="Read Memory",
            description="Read recent entries from memory",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Number of entries to read (0 for all)",
                    }
                },
                "required": [],
            },
            execute=memory_read,
        )
    )

    return tools


# ============================================================================
# Global Registry Instance
# ============================================================================

# Global tool registry instance
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        # Register built-in tools
        for tool in create_built_in_tools():
            _global_registry.register(tool)
    return _global_registry


def reset_tool_registry():
    """Reset the global tool registry."""
    global _global_registry
    _global_registry = None


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    registry = get_tool_registry()
    print(f"Registered tools: {registry.list_tools()}")

    # Example: load skills from directory
    skills_dir = Path("skills")
    if skills_dir.exists():
        registry.load_skills_from_directory(skills_dir)
        print(f"After loading skills: {registry.list_tools()}")
