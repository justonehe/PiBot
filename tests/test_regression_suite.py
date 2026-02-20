from __future__ import annotations

import ast
import py_compile
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compile_or_collect_error(path: Path) -> str | None:
    try:
        py_compile.compile(str(path), doraise=True)
        return None
    except py_compile.PyCompileError as exc:
        return f"{path}: {exc.msg}"


@pytest.mark.parametrize(
    "relative_path",
    [
        "master_hub.py",
        "master_components.py",
        "worker_task_executor.py",
        "agent_core.py",
        "llm_client.py",
        "tool_registry.py",
    ],
)
def test_core_entrypoints_are_syntax_valid(relative_path: str) -> None:
    path = REPO_ROOT / relative_path
    error = _compile_or_collect_error(path)
    assert error is None, error


def test_all_skills_files_are_syntax_valid() -> None:
    skills_dir = REPO_ROOT / "skills"
    skill_files = sorted(skills_dir.glob("*.py"))
    assert skill_files, f"No skill files found in {skills_dir}"

    errors = []
    for path in skill_files:
        error = _compile_or_collect_error(path)
        if error:
            errors.append(error)

    assert not errors, "Syntax errors in skills:\n" + "\n".join(errors)


def test_master_hub_dashboard_helpers_not_redefined() -> None:
    source = (REPO_ROOT / "master_hub.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    target_names = {"get_todos", "get_weather_data", "get_workers_status"}
    occurrences = {name: [] for name in target_names}

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in target_names:
            occurrences[node.name].append(node.lineno)

    duplicates = {
        name: lines for name, lines in occurrences.items() if len(lines) != 1
    }
    assert not duplicates, (
        "Dashboard helper functions should be defined exactly once. "
        f"Found: {duplicates}"
    )


def test_create_default_worker_pool_skips_placeholder_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    import master_components

    monkeypatch.setenv("WORKER_1_IP", "${WORKER_1_IP}")
    monkeypatch.setenv("WORKER_2_IP", "")
    monkeypatch.setenv("WORKER_3_IP", "192.168.10.66")

    pool = master_components.create_default_worker_pool()
    workers = {worker.worker_id: worker.ip for worker in pool.get_all_workers()}

    assert "worker-1" not in workers, workers
    assert workers == {"worker-3": "192.168.10.66"}


def test_worker_route_has_busy_reject_guard() -> None:
    source = (REPO_ROOT / "worker_task_executor.py").read_text(encoding="utf-8")

    start_marker = "def receive_task():"
    end_marker = '@app.route("/task/<task_id>/result", methods=["GET"])'
    start = source.find(start_marker)
    end = source.find(end_marker)

    assert start != -1, "receive_task route function not found"
    assert end != -1 and end > start, "Could not locate receive_task route block"

    receive_task_block = source[start:end]
    assert "_current_task" in receive_task_block, (
        "receive_task should check executor busy state before accepting new tasks"
    )
    assert "409" in receive_task_block, (
        "receive_task should return HTTP 409 when worker is busy"
    )
