"""
PiBot V3 - Master Hub (Robust Edition)
增强健壮性版本，包含完善的错误处理和监控
"""

import os
import json
import time
import subprocess
import threading
import logging
import socket
import sys
from datetime import datetime
from pathlib import Path
from functools import wraps

# ============================================================================
# 1. 日志配置（最先初始化）
# ============================================================================


def setup_logging():
    """Setup logging with rotation and proper formatting."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # 创建 handlers
    handlers = [
        logging.StreamHandler(sys.stdout),
    ]

    # 如果日志目录可写，添加文件 handler
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"master_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        )
        handlers.append(file_handler)
    except Exception as e:
        print(f"Warning: Could not setup file logging: {e}", file=sys.stderr)

    logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)

    return logging.getLogger(__name__)


logger = setup_logging()

# ============================================================================
# 1.5 导入新组件 (Agent Core, TaskPlanner, WorkerPool)
# ============================================================================

try:
    from agent_core import (
        AgentCore,
        AgentContext,
        AgentRole,
        AgentEventStream,
        create_user_message,
    )
    from llm_client import create_llm_client_from_env
    from tool_registry import get_tool_registry
    from master_components import TaskPlanner, create_default_worker_pool

    NEW_COMPONENTS_AVAILABLE = True
    logger.info("New Agent Core components imported successfully")
except ImportError as e:
    NEW_COMPONENTS_AVAILABLE = False
    logger.warning(f"New components not available: {e}")


# ============================================================================
# 2. 配置管理（带验证）
# ============================================================================


class Config:
    """Configuration with validation and defaults."""

    # LLM Configuration
    VOLC_API_KEY = os.environ.get("VOLC_API_KEY", "")
    VOLC_BASE_URL = os.environ.get(
        "VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3"
    )
    MODEL_NAME = os.environ.get("MODEL_NAME", "doubao-seed-code")
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))  # 秒
    LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))

    # Worker Configuration
    WORKER_IP = os.environ.get("WORKER_IP", "192.168.10.66")
    WORKER_USER = os.environ.get("WORKER_USER", "justone")
    INBOX_REMOTE = "~/inbox"
    OUTBOX_REMOTE = "~/outbox"

    # Server Configuration
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    DEBUG = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

    # Memory Configuration
    TAPE_FILE = Path("memory.jsonl")
    MAX_TAPE_SIZE_MB = int(os.environ.get("MAX_TAPE_SIZE_MB", "100"))
    MAX_HISTORY_ENTRIES = int(os.environ.get("MAX_HISTORY_ENTRIES", "50"))

    @classmethod
    def validate(cls):
        """Validate configuration."""
        errors = []

        if not cls.VOLC_API_KEY:
            errors.append("VOLC_API_KEY not set")

        if cls.PORT < 1 or cls.PORT > 65535:
            errors.append(f"Invalid PORT: {cls.PORT}")

        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

        logger.info("Configuration validated successfully")


# ============================================================================
# 3. 健康检查与监控
# ============================================================================


class HealthMonitor:
    """Service health monitoring."""

    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.last_error = None
        self.status = "healthy"

    def record_request(self, success=True):
        """Record a request."""
        self.request_count += 1
        if not success:
            self.error_count += 1
            if self.error_count > 10:  # 阈值
                self.status = "degraded"

    def record_error(self, error):
        """Record an error."""
        self.last_error = {"time": datetime.now().isoformat(), "error": str(error)}

    def get_status(self):
        """Get current health status."""
        uptime = time.time() - self.start_time
        error_rate = self.error_count / max(self.request_count, 1)

        return {
            "status": self.status,
            "uptime_seconds": int(uptime),
            "requests_total": self.request_count,
            "errors_total": self.error_count,
            "error_rate": round(error_rate, 4),
            "last_error": self.last_error,
        }


monitor = HealthMonitor()

# ============================================================================
# 4. 错误处理装饰器
# ============================================================================


def safe_operation(default_return=None, log_errors=True):
    """Decorator for safe operation with error handling."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                monitor.record_error(e)
                monitor.record_request(success=False)
                return default_return

        return wrapper

    return decorator


# ============================================================================
# 5. 记忆管理（健壮版）
# ============================================================================


class MemoryManager:
    """High-performance memory/tape management with caching.

    Optimizations:
    1. Offset caching: Track read position to avoid re-reading entire file
    2. Memory cache: Keep parsed entries in memory for fast access
    3. Incremental reads: Only read new lines since last read
    4. Batch operations: Support batch append for better performance
    """

    def __init__(self, tape_file: Path, max_size_mb: int = 100, cache_size: int = 1000):
        self.tape_file = tape_file
        self.max_size_mb = max_size_mb
        self.cache_size = cache_size
        self._lock = threading.Lock()

        # Performance optimizations
        self._read_offset = 0  # File position for incremental reads
        self._entry_cache: list = []  # In-memory cache
        self._cache_hits = 0
        self._cache_misses = 0

        # Initialize cache from existing file
        self._init_cache()

    def _init_cache(self):
        """Initialize cache from existing file."""
        if not self.tape_file.exists():
            return

        try:
            with self._lock:
                with open(self.tape_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("content") is not None:
                                self._entry_cache.append(entry)
                        except json.JSONDecodeError:
                            continue
                    self._read_offset = f.tell()

            # Trim cache if too large
            if len(self._entry_cache) > self.cache_size:
                self._entry_cache = self._entry_cache[-self.cache_size :]

            logger.info(f"Memory cache initialized: {len(self._entry_cache)} entries")

        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")

    @safe_operation(default_return=None)
    def append(self, role: str, content, meta=None):
        """Append entry to tape with error handling."""
        if not content:
            logger.warning(f"Skipping empty content for role: {role}")
            return None

        entry = {
            "id": int(time.time() * 1000),
            "ts": datetime.now().isoformat(),
            "role": role,
            "content": content,
            "meta": meta or {},
        }

        with self._lock:
            try:
                # Check file rotation first
                self._rotate_if_needed()

                # Write to file
                with open(self.tape_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                # Update cache and offset
                self._entry_cache.append(entry)
                if len(self._entry_cache) > self.cache_size:
                    self._entry_cache.pop(0)  # Remove oldest

                # Update read offset to end of file
                with open(self.tape_file, "r", encoding="utf-8") as f:
                    f.seek(0, 2)  # Seek to end
                    self._read_offset = f.tell()

                logger.debug(
                    f"Appended to tape: {role}, cache size: {len(self._entry_cache)}"
                )
                return entry

            except Exception as e:
                logger.error(f"Failed to write to tape: {e}")
                raise

    @safe_operation(default_return=[])
    def read(self, limit: int = 20):
        """Read entries from tape with caching and incremental reads."""
        if not self.tape_file.exists():
            return []

        try:
            with self._lock:
                # Try to read from cache first if limit is small
                if limit <= len(self._entry_cache):
                    self._cache_hits += 1
                    return self._entry_cache[-limit:]

                # Check if file has been modified (truncated or replaced)
                current_size = self.tape_file.stat().st_size
                if current_size < self._read_offset:
                    # File was truncated, reset cache
                    logger.warning("Tape file was truncated, resetting cache")
                    self._read_offset = 0
                    self._entry_cache = []

                # Read only new lines since last read
                new_entries = []
                with open(self.tape_file, "r", encoding="utf-8") as f:
                    f.seek(self._read_offset)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("content") is not None:
                                new_entries.append(entry)
                                self._entry_cache.append(entry)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping corrupted tape entry: {e}")
                            continue
                    self._read_offset = f.tell()

                # Trim cache if too large
                if len(self._entry_cache) > self.cache_size:
                    excess = len(self._entry_cache) - self.cache_size
                    self._entry_cache = self._entry_cache[excess:]

                self._cache_misses += 1

                # Return from cache
                return self._entry_cache[-limit:]

        except Exception as e:
            logger.error(f"Failed to read tape: {e}")
            return []

    def read_all(self) -> list:
        """Read all entries (for full history export)."""
        return self._entry_cache.copy()

    def clear_cache(self):
        """Clear memory cache (useful for testing)."""
        with self._lock:
            self._entry_cache = []
            self._read_offset = 0
            self._cache_hits = 0
            self._cache_misses = 0
        logger.info("Memory cache cleared")

    def _rotate_if_needed(self):
        """Rotate tape file if too large."""
        if not self.tape_file.exists():
            return

        size_mb = self.tape_file.stat().st_size / (1024 * 1024)
        if size_mb > self.max_size_mb:
            logger.info(f"Rotating tape file (size: {size_mb:.1f}MB)")
            backup = self.tape_file.with_suffix(
                f".jsonl.{datetime.now().strftime('%Y%m%d')}.backup"
            )
            self.tape_file.rename(backup)
            # Reset cache for new file
            self._entry_cache = []
            self._read_offset = 0
            self.tape_file.write_text("")

    def get_stats(self):
        """Get tape statistics including cache performance."""
        if not self.tape_file.exists():
            return {
                "exists": False,
                "entries": 0,
                "size_mb": 0,
                "cache_entries": len(self._entry_cache),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
            }

        try:
            size_mb = self.tape_file.stat().st_size / (1024 * 1024)
            with open(self.tape_file, "r", encoding="utf-8") as f:
                lines = sum(1 for _ in f)

            hit_rate = self._cache_hits / max(self._cache_hits + self._cache_misses, 1)

            return {
                "exists": True,
                "entries": lines,
                "size_mb": round(size_mb, 2),
                "cache_entries": len(self._entry_cache),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": round(hit_rate, 2),
            }
        except Exception as e:
            logger.error(f"Failed to get tape stats: {e}")
            return {"exists": True, "error": str(e)}


# Initialize memory manager
memory = MemoryManager(Config.TAPE_FILE, Config.MAX_TAPE_SIZE_MB)

# ============================================================================
# 6. LLM 客户端（带重试和超时）
# ============================================================================


class LLMClient:
    """Robust LLM client with retry logic."""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=Config.VOLC_API_KEY,
                base_url=Config.VOLC_BASE_URL,
                timeout=Config.LLM_TIMEOUT,
            )
            logger.info("LLM client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            self.client = None

    def is_available(self):
        """Check if client is available."""
        return self.client is not None

    @safe_operation(default_return=None)
    def chat(self, messages, model=None, max_retries=None):
        """Chat with retry logic."""
        if not self.client:
            return None

        model = model or Config.MODEL_NAME
        max_retries = max_retries or Config.LLM_MAX_RETRIES

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model, messages=messages
                )
                return response

            except Exception as e:
                last_error = e
                logger.warning(f"LLM attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    time.sleep(2**attempt)  # 指数退避

        logger.error(f"LLM failed after {max_retries + 1} attempts: {last_error}")
        return None


llm = LLMClient()

# ============================================================================
# 7. 工具函数
# ============================================================================


@safe_operation(default_return="127.0.0.1")
def get_local_ip():
    """Get local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


@safe_operation(default_return={"status": "error", "error": "dispatch failed"})
def dispatch_task(cmd):
    """Dispatch task to worker."""
    task_id = f"task-{int(time.time())}"
    task_payload = {"id": task_id, "cmd": cmd, "ts": time.time()}
    local_file = f"/tmp/{task_id}.json"

    with open(local_file, "w") as f:
        json.dump(task_payload, f)

    scp_cmd = f"scp -o StrictHostKeyChecking=no -o ConnectTimeout=5 {local_file} {Config.WORKER_USER}@{Config.WORKER_IP}:{Config.INBOX_REMOTE}/{task_id}.json"
    result = subprocess.run(scp_cmd, shell=True, capture_output=True, timeout=10)

    if result.returncode == 0:
        return {"status": "dispatched", "id": task_id}
    else:
        return {"status": "error", "error": result.stderr.decode()}


# ============================================================================
# 8. Dashboard Data Functions
# ============================================================================

# Dashboard data storage
DASHBOARD_DATA_FILE = Path("dashboard_data.json")


def get_dashboard_data():
    """Get dashboard data from shared file (can be updated by Agent)."""
    if not DASHBOARD_DATA_FILE.exists():
        # Return default data if file doesn't exist
        return {
            "weather": {
                "location": "Shanghai",
                "current": {
                    "temp": 22,
                    "condition": "sunny",
                    "humidity": 65,
                    "wind": "3级",
                },
                "forecast": [
                    {"day": "明天", "condition": "cloudy", "high": 23, "low": 18},
                    {"day": "后天", "condition": "rainy", "high": 20, "low": 16},
                    {"day": "周五", "condition": "sunny", "high": 25, "low": 19},
                ],
            },
            "todos": [],
            "workers": [
                {
                    "id": "worker_1",
                    "name": "Worker-1",
                    "status": "idle",
                    "statusText": "闲置",
                },
                {
                    "id": "worker_2",
                    "name": "Worker-2",
                    "status": "offline",
                    "statusText": "离线",
                },
                {
                    "id": "worker_3",
                    "name": "Worker-3",
                    "status": "offline",
                    "statusText": "离线",
                },
            ],
            "system_message": "",
            "last_updated": datetime.now().isoformat(),
        }

    try:
        with open(DASHBOARD_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return (
            get_dashboard_data.__wrapped__()
            if hasattr(get_dashboard_data, "__wrapped__")
            else {
                "weather": {
                    "location": "Error",
                    "current": {"temp": 0, "condition": "sunny"},
                    "forecast": [],
                },
                "todos": [],
                "workers": [],
            }
        )


def get_todos():
    """Get todos from dashboard data."""
    return get_dashboard_data().get("todos", [])


def get_weather_data():
    """Get weather from dashboard data."""
    return get_dashboard_data().get("weather", {})


def get_workers_status():
    """Get workers from dashboard data."""
    return get_dashboard_data().get("workers", [])


# ============================================================================

# Todo storage (simple JSON file)
TODO_FILE = Path("todos.json")


def load_todos():
    """Load todos from file."""
    if not TODO_FILE.exists():
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_todos(todos):
    """Save todos to file."""
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def get_todos():
    """Get all todos."""
    return load_todos()


def add_todo(text):
    """Add a new todo."""
    todos = load_todos()
    todo = {
        "id": int(time.time() * 1000),
        "text": text,
        "done": False,
        "created": datetime.now().isoformat(),
    }
    todos.append(todo)
    save_todos(todos)
    return todo


def delete_todo(todo_id):
    """Delete a todo."""
    todos = load_todos()
    todos = [t for t in todos if t["id"] != todo_id]
    save_todos(todos)
    return True


def toggle_todo_status(todo_id):
    """Toggle todo done status."""
    todos = load_todos()
    for todo in todos:
        if todo["id"] == todo_id:
            todo["done"] = not todo.get("done", False)
            save_todos(todos)
            return True
    return False


# Weather data (mock for now, can be replaced with real API)
_last_weather_update = 0
_weather_cache = None


def get_weather_data():
    """Get weather data (with caching)."""
    global _last_weather_update, _weather_cache

    # Cache for 10 minutes
    if _weather_cache and (time.time() - _last_weather_update) < 600:
        return _weather_cache

    # TODO: Replace with real weather API
    # For now, return mock data
    weather = {
        "location": "Shanghai",
        "current": {
            "temp": 22,
            "condition": "sunny",
            "humidity": 65,
            "wind": "3级",
        },
        "forecast": [
            {"day": "明天", "condition": "cloudy", "high": 23, "low": 18},
            {"day": "后天", "condition": "rainy", "high": 20, "low": 16},
            {"day": "周五", "condition": "sunny", "high": 25, "low": 19},
        ],
    }

    _weather_cache = weather
    _last_weather_update = time.time()
    return weather


# Worker status tracking
_workers_status = {
    "worker_1": {
        "name": "Worker-1",
        "status": "idle",
        "statusText": "闲置",
        "last_seen": None,
    },
    "worker_2": {
        "name": "Worker-2",
        "status": "offline",
        "statusText": "离线",
        "last_seen": None,
    },
    "worker_3": {
        "name": "Worker-3",
        "status": "offline",
        "statusText": "离线",
        "last_seen": None,
    },
}


def get_workers_status():
    """Get workers status."""
    # TODO: Add real worker health check
    # For now, return configured workers
    return [
        {
            "id": "worker_1",
            "name": _workers_status["worker_1"]["name"],
            "status": _workers_status["worker_1"]["status"],
            "statusText": _workers_status["worker_1"]["statusText"],
        },
        {
            "id": "worker_2",
            "name": _workers_status["worker_2"]["name"],
            "status": _workers_status["worker_2"]["status"],
            "statusText": _workers_status["worker_2"]["statusText"],
        },
        {
            "id": "worker_3",
            "name": _workers_status["worker_3"]["name"],
            "status": _workers_status["worker_3"]["status"],
            "statusText": _workers_status["worker_3"]["statusText"],
        },
    ]


def update_worker_status(worker_id, status, status_text):
    """Update worker status."""
    if worker_id in _workers_status:
        _workers_status[worker_id]["status"] = status
        _workers_status[worker_id]["statusText"] = status_text
        _workers_status[worker_id]["last_seen"] = datetime.now().isoformat()


# ============================================================================
# 9. Flask 应用
# ============================================================================

try:
    from flask import Flask, request, jsonify, render_template_string

    flask_available = True
except ImportError:
    logger.error("Flask not available")
    flask_available = False
    Flask = None

if flask_available:
    app = Flask(__name__)

    HTML_BASE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>{{ title }}</title>
    <style>
        :root { --primary: #007aff; --bg: #f2f2f7; --card: #ffffff; --text: #1c1c1e; }
        body { font-family: -apple-system, sans-serif; background: var(--bg); margin: 0; display: flex; flex-direction: column; height: 100vh; color: var(--text); }
        .header { background: var(--card); padding: 15px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }
        #chat-container { flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 10px; background: #fff; }
        .message { padding: 10px 14px; white-space: pre-wrap; border-radius: 18px; max-width: 80%; line-height: 1.4; word-wrap: break-word; font-size: 15px; }
        .user { align-self: flex-end; background: var(--primary); color: #fff; border-bottom-right-radius: 4px; }
        .assistant { align-self: flex-start; background: #e9e9eb; color: #000; border-bottom-left-radius: 4px; }
        .sys { align-self: center; font-size: 0.8em; color: #8e8e93; background: #f0f0f0; padding: 2px 10px; border-radius: 10px; }
        .input-area { padding: 10px; background: var(--card); border-top: 1px solid #ddd; display: flex; gap: 10px; }
        #user-input { flex: 1; padding: 12px; border-radius: 20px; border: 1px solid #ddd; font-size: 16px; outline: none; }
        #send-btn { background: var(--primary); color: white; border: none; padding: 0 15px; border-radius: 20px; font-weight: bold; }
        .error { background: #ffebee; color: #c62828; align-self: center; }
    </style>
</head>
<body>
    <div class="header">
        <span style="font-weight:bold;">🤖 {{ title }}</span>
        <span style="font-size:0.8em; color:gray;">{{ ip }}</span>
    </div>
    <div id="chat-container"></div>
    <div class="input-area">
        <input type="text" id="user-input" placeholder="输入指令..." autocomplete="off">
        <button id="send-btn">发送</button>
    </div>
    <script>
        const chat = document.getElementById('chat-container');
        const input = document.getElementById('user-input');
        const btn = document.getElementById('send-btn');
        let lastUpdate = 0;

        function appendMsg(role, text) {
            const div = document.createElement('div');
            div.className = `message ${role}`;
            let html = text
                .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, src) => `<img src="${src}" alt="${alt}" style="max-width:100%; border-radius:8px; margin:4px 0;">`)
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, url) => `<a href="${url}" target="_blank">${text}</a>`)
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/`([^`]+)`/g, '<code style="background:#f0f0f0; padding:2px 6px; border-radius:4px;">$1</code>');
            div.innerHTML = html;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history?t=' + Date.now());
                const data = await res.json();
                if (data.timestamp > lastUpdate) {
                    chat.innerHTML = '';
                    data.history.forEach(m => appendMsg(m.role, m.content));
                    lastUpdate = data.timestamp;
                }
            } catch(e) { console.error('History load failed:', e); }
        }

        async function send() {
            const val = input.value.trim();
            if(!val) return;
            input.value = '';
            appendMsg('user', val);
            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({msg: val})
                });
                const data = await res.json();
                if (data.error) {
                    appendMsg('error', '⚠️ ' + data.error);
                }
                setTimeout(loadHistory, 800);
            } catch(e) { 
                appendMsg('error', '⚠️ 发送失败，请检查网络'); 
                console.error('Send failed:', e);
            }
        }

        btn.onclick = send;
        input.onkeypress = (e) => { if(e.key === 'Enter') send(); };
        setInterval(loadHistory, 3000);
        loadHistory();
    </script>
</body>
</html>
"""

    @app.route("/")
    def index():
        return render_template_string(
            HTML_BASE, title="PiBot Desktop", ip=get_local_ip()
        )

    @app.route("/mobile")
    def mobile():
        return render_template_string(
            HTML_BASE, title="PiBot Mobile", ip=get_local_ip()
        )

    @app.route("/api/health")
    def health():
        """Health check endpoint."""
        return jsonify(
            {
                **monitor.get_status(),
                "llm_available": llm.is_available(),
                "tape_stats": memory.get_stats(),
            }
        )

    @app.route("/api/history")
    def api_history():
        history = memory.read(20)
        try:
            ts = os.path.getmtime(Config.TAPE_FILE) if Config.TAPE_FILE.exists() else 0
        except:
            ts = 0
        return jsonify({"history": history, "timestamp": ts})

    @app.route("/api/chat", methods=["POST"])
    def chat():
        monitor.record_request()

        # Parse request with error handling
        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            logger.error(f"Failed to parse request: {e}")
            monitor.record_error(e)
            return jsonify({"reply": "", "error": "Invalid request format"})

        user_msg = data.get("msg", "").strip()
        if not user_msg:
            return jsonify({"reply": "", "error": "Empty message"})

        # Save to memory
        memory.append("user", user_msg)

        # Check LLM availability
        if not llm.is_available():
            error_msg = "LLM service not available"
            logger.error(error_msg)
            return jsonify({"reply": "", "error": error_msg})

        # Load skills
        skill_mgr = None
        skill_prompt = ""
        try:
            from skill_manager import SkillManager

            skill_mgr = SkillManager()
            skill_mgr.load_skills()
            skill_prompt = skill_mgr.get_prompt()
        except Exception as e:
            logger.error(f"Skill error: {e}")

        # Build conversation
        history = memory.read(Config.MAX_HISTORY_ENTRIES)
        system_prompt = f"""你是 Master Agent。你可以使用以下技能来完成任务：

{skill_prompt}

重要提示：
- 当使用技能时，技能会返回结构化数据
- 你应该分析技能返回的数据，并为用户提供清晰、有用的回复
- 不要直接返回原始数据给用户，要提供总结和解释
- 保持对话上下文，参考之前的对话内容

请根据用户的问题和可用技能提供最佳回答。"""

        messages = [{"role": "system", "content": system_prompt}]
        for entry in history:
            role = entry.get("role")
            content = entry.get("content")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_msg})

        # Call LLM
        response = llm.chat(messages)
        if not response:
            error_msg = "Failed to get response from LLM"
            logger.error(error_msg)
            return jsonify({"reply": "", "error": error_msg})

        ai_reply = response.choices[0].message.content

        # Handle skill calls with multi-step execution
        max_iterations = 10  # 防止无限循环
        iteration = 0
        current_reply = ai_reply

        while (
            "<call_skill>" in current_reply and skill_mgr and iteration < max_iterations
        ):
            iteration += 1
            logger.info(f"Executing skill call (iteration {iteration})")

            try:
                start = current_reply.find("<call_skill>") + 12
                end = current_reply.find("</call_skill>")
                content = current_reply[start:end].strip()

                if ":" in content:
                    skill_name, args = content.split(":", 1)
                    skill_result = skill_mgr.execute(skill_name, args)
                else:
                    skill_result = skill_mgr.execute(content)

                # Follow-up with skill result
                messages.append({"role": "assistant", "content": current_reply})
                messages.append(
                    {
                        "role": "user",
                        "content": f"技能执行结果：{json.dumps(skill_result, ensure_ascii=False)}\n\n请根据这个结果继续完成任务。如果需要执行更多操作，请继续使用 <call_skill> 标签。",
                    }
                )

                # 继续对话以检查是否需要更多步骤
                next_response = llm.chat(messages)
                if next_response:
                    current_reply = next_response.choices[0].message.content
                    logger.info(
                        f"LLM response after skill execution (iteration {iteration})"
                    )
                else:
                    break

            except Exception as e:
                logger.error(f"Skill execution error (iteration {iteration}): {e}")
                break

        # 保存最终回复到记忆
        memory.append("assistant", current_reply)

        # 如果执行了多步，添加执行信息
        if iteration > 0:
            logger.info(f"Multi-step execution completed: {iteration} iterations")
            return jsonify({"reply": current_reply, "steps": iteration})

        return jsonify({"reply": current_reply})

    # ============================================================================
    # Dashboard Routes
    # ============================================================================

    DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PiBot Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: auto auto 1fr;
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }
        .header {
            grid-column: 1 / -1;
            text-align: center;
            color: white;
            padding: 20px;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .datetime { font-size: 1.2em; opacity: 0.9; }
        .weather-current {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .weather-icon { font-size: 4em; }
        .weather-info h2 { font-size: 3em; margin-bottom: 5px; }
        .weather-info p { color: #666; font-size: 1.1em; }
        .weather-forecast {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        .forecast-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 15px;
        }
        .forecast-day {
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 12px;
        }
        .forecast-day .day { font-weight: bold; color: #667eea; }
        .forecast-day .icon { font-size: 2em; margin: 10px 0; }
        .forecast-day .temp { font-size: 1.2em; }
        .section-title {
            font-size: 1.3em;
            font-weight: bold;
            margin-bottom: 15px;
            color: #667eea;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .todo-list {
            list-style: none;
        }
        .todo-item {
            display: flex;
            align-items: center;
            padding: 12px;
            margin-bottom: 8px;
            background: #f8f9fa;
            border-radius: 10px;
            transition: all 0.3s;
        }
        .todo-item:hover { background: #e9ecef; }
        .todo-checkbox {
            width: 20px;
            height: 20px;
            margin-right: 12px;
            cursor: pointer;
        }
        .todo-text { flex: 1; }
        .todo-text.done { text-decoration: line-through; color: #999; }
        .workers-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }
        .worker-card {
            text-align: center;
            padding: 20px;
            border-radius: 12px;
            background: #f8f9fa;
            transition: all 0.3s;
        }
        .worker-card.active {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }
        .worker-card.idle {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .worker-card.offline {
            background: #e9ecef;
            color: #999;
        }
        .worker-icon { font-size: 2.5em; margin-bottom: 10px; }
        .worker-name { font-weight: bold; margin-bottom: 5px; }
        .worker-status { font-size: 0.9em; opacity: 0.9; }
        .loading { text-align: center; color: #999; padding: 20px; }
        .error { background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; }
        @media (max-width: 768px) {
            .dashboard { grid-template-columns: 1fr; }
            .forecast-grid, .workers-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>🤖 PiBot Dashboard</h1>
            <div class="datetime" id="datetime">Loading...</div>
        </div>

        <div class="card">
            <div class="section-title">🌤️ 天气</div>
            <div id="weather-content">
                <div class="loading">Loading weather...</div>
            </div>
        </div>

        <div class="card">
            <div class="section-title">📝 待办事项</div>
            <ul class="todo-list" id="todo-list">
                <li class="loading">Loading todos...</li>
            </ul>
        </div>

        <div class="card" style="grid-column: 1 / -1;">
            <div class="section-title">👷 Worker 状态</div>
            <div class="workers-grid" id="workers-grid">
                <div class="loading">Loading workers...</div>
            </div>
        </div>
    </div>

    <script>
        // Prevent any redirects
        window.onbeforeunload = function(e) {
            e.preventDefault();
            e.returnValue = '';
            return '';
        };
        
        // Override any existing location change attempts
        Object.defineProperty(window, 'location', {
            writable: false,
            value: window.location
        });
        
        // Block history manipulation
        const originalPushState = history.pushState;
        history.pushState = function() {
            console.log('Blocked pushState redirect');
            return null;
        };
        
        const originalReplaceState = history.replaceState;
        history.replaceState = function() {
            console.log('Blocked replaceState redirect');
            return null;
        };
        
        // Update datetime
        function updateDateTime() {
            const now = new Date();
            const options = {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                weekday: 'long',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            };
            document.getElementById('datetime').textContent = now.toLocaleString('zh-CN', options);
        }
        setInterval(updateDateTime, 1000);
        updateDateTime();

        // Fetch dashboard data
        async function loadDashboardData() {
            try {
                const res = await fetch('/api/dashboard/data?t=' + Date.now());
                const data = await res.json();

                // Update weather
                if (data.weather) {
                    updateWeather(data.weather);
                }

                // Update todos
                if (data.todos) {
                    updateTodos(data.todos);
                }

                // Update workers
                if (data.workers) {
                    updateWorkers(data.workers);
                }
            } catch (e) {
                console.error('Failed to load dashboard:', e);
            }
        }

        function updateWeather(weather) {
            const icons = {
                'sunny': '☀️', 'cloudy': '☁️', 'rainy': '🌧️',
                'snowy': '❄️', 'stormy': '⛈️', 'foggy': '🌫️'
            };
            const html = `
                <div class="weather-current">
                    <div class="weather-icon">${icons[weather.current?.condition] || '🌤️'}</div>
                    <div class="weather-info">
                        <h2>${weather.current?.temp || '--'}°C</h2>
                        <p>${weather.current?.condition || 'Unknown'} | 湿度 ${weather.current?.humidity || '--'}%</p>
                        <p>${weather.location || 'Unknown Location'}</p>
                    </div>
                </div>
                <div class="weather-forecast">
                    <div class="section-title" style="font-size: 1em;">📅 未来3天</div>
                    <div class="forecast-grid">
                        ${(weather.forecast || []).map(day => `
                            <div class="forecast-day">
                                <div class="day">${day.day}</div>
                                <div class="icon">${icons[day.condition] || '🌤️'}</div>
                                <div class="temp">${day.high}° / ${day.low}°</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            document.getElementById('weather-content').innerHTML = html;
        }

        function updateTodos(todos) {
            if (todos.length === 0) {
                document.getElementById('todo-list').innerHTML = '<li class="loading">暂无待办事项</li>';
                return;
            }
            const html = todos.map(todo => `
                <li class="todo-item">
                    <input type="checkbox" class="todo-checkbox" ${todo.done ? 'checked' : ''} disabled>
                    <span class="todo-text ${todo.done ? 'done' : ''}">${todo.text}</span>
                </li>
            `).join('');
            document.getElementById('todo-list').innerHTML = html;
        }

        function updateWorkers(workers) {
            const html = workers.map(worker => `
                <div class="worker-card ${worker.status}">
                    <div class="worker-icon">${worker.status === 'active' ? '🔥' : worker.status === 'idle' ? '💤' : '❌'}</div>
                    <div class="worker-name">${worker.name}</div>
                    <div class="worker-status">${worker.statusText}</div>
                </div>
            `).join('');
            document.getElementById('workers-grid').innerHTML = html;
        }

        // Load initially and refresh every 30 seconds
        loadDashboardData();
        setInterval(loadDashboardData, 30000);
    </script>
</body>
</html>
"""

    @app.route("/dashboard")
    def dashboard():
        """Dashboard display - server-side rendered, no JavaScript."""
        data = get_dashboard_data()
        weather = data.get("weather", {})
        current = weather.get("current", {})
        forecast = weather.get("forecast", [])
        todos = data.get("todos", [])
        workers = data.get("workers", [])

        from datetime import datetime

        now = datetime.now()
        # 简化日期显示适配7寸屏: 02-19 周三 14:30
        datetime_str = now.strftime("%m-%d %a %H:%M")

        weather_icons = {
            "sunny": "☀️",
            "cloudy": "☁️",
            "rainy": "🌧️",
            "snowy": "❄️",
            "stormy": "⛈️",
            "foggy": "🌫️",
        }
        w_icon = weather_icons.get(current.get("condition"), "🌤️")
        w_temp = current.get("temp", "--")
        w_humidity = current.get("humidity", "--")
        w_location = weather.get("location", "Unknown")

        # Build forecast HTML
        forecast_html = ""
        for day in forecast:
            d_icon = weather_icons.get(day.get("condition"), "🌤️")
            forecast_html += f"<div style='text-align:center;padding:15px;background:#f8f9fa;border-radius:12px;'><div style='font-weight:bold;color:#667eea;'>{day.get('day', '')}</div><div style='font-size:2em;margin:10px 0;'>{d_icon}</div><div>{day.get('high', '--')}° / {day.get('low', '--')}°</div></div>"

        # Build todos HTML
        todos_html = ""
        if not todos:
            todos_html = "<li style='padding:12px;background:#f8f9fa;border-radius:10px;margin-bottom:8px;'>暂无待办事项</li>"
        else:
            for todo in todos:
                done_style = (
                    "text-decoration:line-through;color:#999;"
                    if todo.get("done")
                    else ""
                )
                todos_html += f"<li style='padding:12px;background:#f8f9fa;border-radius:10px;margin-bottom:8px;{done_style}'>☐ {todo.get('text', '')}</li>"

        # Build workers HTML
        workers_html = ""
        for worker in workers:
            status = worker.get("status", "offline")
            icon = "🔥" if status == "active" else ("💤" if status == "idle" else "❌")
            bg = (
                "linear-gradient(135deg,#11998e 0%,#38ef7d 100%);color:white;"
                if status == "active"
                else (
                    "linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;"
                    if status == "idle"
                    else "#f8f9fa;"
                )
            )
            workers_html += f"<div style='text-align:center;padding:20px;border-radius:12px;background:{bg}'><div style='font-size:2.5em;margin-bottom:10px;'>{icon}</div><div style='font-weight:bold;'>{worker.get('name', '')}</div><div>{worker.get('statusText', '')}</div></div>"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PiBot Dashboard</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #333; min-height: 100vh; padding: 8px; margin: 0; font-size: 14px; overflow-x: hidden; }}
        .dashboard {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; max-width: 800px; margin: 0 auto; }}
        .card {{ background: rgba(255,255,255,0.95); border-radius: 8px; padding: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ grid-column: 1 / -1; text-align: center; color: white; padding: 8px 4px; }}
        .header h1 {{ font-size: 1.6em; margin: 0 0 4px 0; }}
        .datetime {{ font-size: 0.9em; opacity: 0.9; }}
        .section-title {{ font-size: 1em; font-weight: bold; margin-bottom: 8px; color: #667eea; display: flex; align-items: center; gap: 4px; }}
        .weather-current {{ display: flex; align-items: center; gap: 10px; }}
        .weather-icon {{ font-size: 2.5em; line-height: 1; }}
        .weather-info h2 {{ font-size: 2em; margin: 0; line-height: 1.2; }}
        .weather-info p {{ font-size: 0.85em; margin: 2px 0; color: #666; }}
        .forecast-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 8px; }}
        .forecast-day {{ text-align: center; padding: 6px 4px; background: #f8f9fa; border-radius: 6px; font-size: 0.8em; }}
        .forecast-day .day {{ font-weight: bold; color: #667eea; font-size: 0.9em; }}
        .forecast-day .icon {{ font-size: 1.5em; margin: 4px 0; line-height: 1; display: block; }}
        .forecast-day .temp {{ font-size: 0.85em; }}
        .todo-list {{ list-style: none; padding: 0; margin: 0; max-height: 150px; overflow-y: auto; }}
        .todo-item {{ display: flex; align-items: center; padding: 6px 8px; margin-bottom: 4px; background: #f8f9fa; border-radius: 6px; font-size: 0.9em; }}
        .todo-checkbox {{ width: 14px; height: 14px; margin-right: 8px; flex-shrink: 0; }}
        .todo-text {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .todo-text.done {{ text-decoration: line-through; color: #999; }}
        .workers-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
        .worker-card {{ text-align: center; padding: 10px 6px; border-radius: 8px; font-size: 0.85em; }}
        .worker-card.active {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; }}
        .worker-card.idle {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
        .worker-card.offline {{ background: #e9ecef; color: #666; }}
        .worker-icon {{ font-size: 1.8em; margin-bottom: 4px; line-height: 1; display: block; }}
        .worker-name {{ font-weight: bold; margin-bottom: 2px; font-size: 0.9em; }}
        .worker-status {{ font-size: 0.8em; opacity: 0.9; }}
        .loading {{ text-align: center; color: #999; padding: 10px; font-size: 0.9em; }}
        
        /* 7寸屏幕优化 - 800x480 */
        @media (max-width: 800px) {{
            body {{ padding: 6px; font-size: 13px; }}
            .dashboard {{ gap: 6px; }}
            .card {{ padding: 10px; border-radius: 6px; }}
            .header h1 {{ font-size: 1.4em; }}
            .datetime {{ font-size: 0.8em; }}
            .section-title {{ font-size: 0.95em; margin-bottom: 6px; }}
            .weather-icon {{ font-size: 2em; }}
            .weather-info h2 {{ font-size: 1.6em; }}
            .forecast-grid {{ gap: 4px; }}
            .forecast-day {{ padding: 4px 2px; font-size: 0.75em; }}
            .forecast-day .icon {{ font-size: 1.3em; margin: 2px 0; }}
            .workers-grid {{ gap: 6px; }}
            .worker-card {{ padding: 8px 4px; }}
            .worker-icon {{ font-size: 1.5em; }}
        }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>🤖 PiBot Dashboard</h1>
            <div style="font-size: 1.2em; opacity: 0.9;">{datetime_str}</div>
        </div>
        <div class="card">
            <div class="section-title">🌤️ 天气 - {w_location}</div>
            <div class="weather-current">
                <div class="weather-icon">{w_icon}</div>
                <div class="weather-info">
                    <h2>{w_temp}°C</h2>
                    <p>湿度 {w_humidity}%</p>
                </div>
            </div>
            <div class="forecast-grid">{forecast_html}</div>
        </div>
        <div class="card">
            <div class="section-title">📝 待办事项 ({len(todos)})</div>
            <ul class="todo-list">{todos_html}</ul>
        </div>
        <div class="card" style="grid-column: 1 / -1;">
            <div class="section-title">👷 Worker 状态</div>
            <div class="workers-grid">{workers_html}</div>
        </div>
    </div>
</body>
</html>"""
        return html

    @app.route("/api/dashboard/data")
    def dashboard_data():
        """API endpoint for dashboard data."""
        return jsonify(
            {
                "weather": get_weather_data(),
                "todos": get_todos(),
                "workers": get_workers_status(),
            }
        )

    @app.route("/api/todos", methods=["GET", "POST", "DELETE"])
    def manage_todos():
        """Manage todo items."""
        if request.method == "GET":
            return jsonify({"todos": get_todos()})

        elif request.method == "POST":
            data = request.get_json() or {}
            text = data.get("text", "").strip()
            if not text:
                return jsonify({"success": False, "error": "Empty todo text"})

            todo = add_todo(text)
            return jsonify({"success": True, "todo": todo})

        elif request.method == "DELETE":
            data = request.get_json() or {}
            todo_id = data.get("id")
            if todo_id is None:
                return jsonify({"success": False, "error": "Missing todo id"})

            success = delete_todo(todo_id)
            return jsonify({"success": success})

    @app.route("/api/todos/<int:todo_id>/toggle", methods=["POST"])
    def toggle_todo(todo_id):
        """Toggle todo done status."""
        success = toggle_todo_status(todo_id)
        return jsonify({"success": success})

# ============================================================================
# 9. 主入口
# ============================================================================

if __name__ == "__main__":
    try:
        Config.validate()

        if not flask_available:
            logger.error("Flask is required but not available")
            sys.exit(1)

        logger.info(f"Starting Master Hub on {Config.HOST}:{Config.PORT}")
        logger.info(f"Health check: http://{Config.HOST}:{Config.PORT}/api/health")

        app.run(host=Config.HOST, port=Config.PORT, threaded=True, debug=Config.DEBUG)

    except Exception as e:
        logger.critical(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)
