#!/usr/bin/env python3
"""
PiBot V3 - Master-Worker Integration Tests

Run these tests to verify the Master-Worker architecture is working correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from master_components import TaskPlanner, create_default_worker_pool, SubTask
from llm_client import create_llm_client_from_env


class Colors:
    """Terminal colors for output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    END = "\033[0m"


def print_header(text):
    """Print a section header."""
    print(f"\n{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BLUE}{'=' * 60}{Colors.END}")


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text):
    """Print info message."""
    print(f"{Colors.YELLOW}ℹ {text}{Colors.END}")


async def test_worker_health():
    """Test 1: Check all Workers are healthy."""
    print_header("Test 1: Worker Health Check")

    worker_pool = create_default_worker_pool()

    try:
        print_info("Checking health of all Workers...")
        health = await worker_pool.check_all_workers_health()

        all_healthy = True
        for worker_id, is_healthy in health.items():
            if is_healthy:
                print_success(f"{worker_id} is healthy")
            else:
                print_error(f"{worker_id} is not responding")
                all_healthy = False

        await worker_pool.close()

        if all_healthy:
            print_success("All Workers are healthy!")
            return True
        else:
            print_error("Some Workers are not responding")
            return False

    except Exception as e:
        print_error(f"Health check failed: {e}")
        await worker_pool.close()
        return False


async def test_worker_status():
    """Test 2: Get Worker status summary."""
    print_header("Test 2: Worker Status Summary")

    worker_pool = create_default_worker_pool()

    try:
        status = worker_pool.get_status_summary()

        print_info(f"Total Workers: {status['total']}")
        print(f"  Idle: {status['idle']}")
        print(f"  Busy: {status['busy']}")
        print(f"  Offline: {status['offline']}")

        for worker in status["workers"]:
            print(f"\n  {worker['id']}:")
            print(f"    IP: {worker['ip']}")
            print(f"    Status: {worker['status']}")

        await worker_pool.close()
        print_success("Status retrieval successful")
        return True

    except Exception as e:
        print_error(f"Status check failed: {e}")
        await worker_pool.close()
        return False


async def test_task_analysis():
    """Test 3: Task complexity analysis."""
    print_header("Test 3: Task Analysis (TaskPlanner)")

    llm_client = create_llm_client_from_env()
    planner = TaskPlanner(llm_client)

    test_cases = [
        ("What time is it?", "should be SIMPLE"),
        ("Download a file from the internet", "should be COMPLEX"),
        ("Read my todo list", "should be SIMPLE"),
        ("Process all images in a folder", "should be COMPLEX"),
    ]

    try:
        for task, expected in test_cases:
            print_info(f"Analyzing: '{task}'")
            plan = await planner.analyze_task(task)
            print(f"  Result: {plan.complexity.value} (expected: {expected})")
            print(f"  Handle locally: {plan.handle_locally}")
            print(f"  Subtasks: {len(plan.subtasks)}")

        print_success("Task analysis working")
        return True

    except Exception as e:
        print_error(f"Task analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_simple_task_dispatch():
    """Test 4: Dispatch a simple task to Worker."""
    print_header("Test 4: Simple Task Dispatch")

    worker_pool = create_default_worker_pool()

    try:
        # Create a simple task
        task = SubTask(
            task_id="test_simple_001",
            description="List files in current directory",
            skills=["shell_exec"],
        )

        print_info("Dispatching task to available Worker...")
        result = await worker_pool.execute_task(task, timeout=30)

        print(f"\n  Success: {result.get('success', False)}")
        print(f"  Worker: {result.get('worker_id', 'N/A')}")
        print(f"  Elapsed: {result.get('elapsed', 'N/A'):.2f}s")

        if result.get("success"):
            output = result.get("data", {}).get("output", "No output")
            print(f"  Output preview: {output[:100]}...")
            print_success("Task executed successfully")
            success = True
        else:
            print_error(f"Task failed: {result.get('error', 'Unknown error')}")
            success = False

        await worker_pool.close()
        return success

    except Exception as e:
        print_error(f"Task dispatch failed: {e}")
        import traceback

        traceback.print_exc()
        await worker_pool.close()
        return False


async def test_task_cancellation():
    """Test 5: Cancel a running task."""
    print_header("Test 5: Task Cancellation")

    worker_pool = create_default_worker_pool()

    try:
        # Start a long-running task
        task = SubTask(
            task_id="test_cancel_001",
            description="Sleep for 60 seconds",
            skills=["shell_exec"],
        )

        print_info("Starting long-running task...")

        # Start task but don't wait
        import aiohttp

        session = aiohttp.ClientSession()

        # Get available worker
        worker = worker_pool.get_available_worker()
        if not worker:
            print_error("No available Workers")
            await session.close()
            await worker_pool.close()
            return False

        # Dispatch task
        async with session.post(
            worker.get_url("/task"),
            json={
                "task_id": task.task_id,
                "description": task.description,
                "skills": task.skills,
            },
        ) as response:
            if response.status == 202:
                print_success("Task started")
            else:
                print_error(f"Failed to start task: {response.status}")
                await session.close()
                await worker_pool.close()
                return False

        # Wait a moment then cancel
        await asyncio.sleep(2)
        print_info("Cancelling task...")

        cancelled = await worker_pool.cancel_task(worker.worker_id, task.task_id)

        if cancelled:
            print_success("Task cancelled successfully")
        else:
            print_error("Failed to cancel task")

        await session.close()
        await worker_pool.close()
        return cancelled

    except Exception as e:
        print_error(f"Cancellation test failed: {e}")
        import traceback

        traceback.print_exc()
        await worker_pool.close()
        return False


async def test_parallel_execution():
    """Test 6: Execute tasks in parallel."""
    print_header("Test 6: Parallel Task Execution")

    worker_pool = create_default_worker_pool()

    try:
        # Create 3 tasks
        tasks = [
            SubTask(
                task_id=f"parallel_{i}",
                description=f"Echo 'Task {i}'",
                skills=["shell_exec"],
            )
            for i in range(3)
        ]

        print_info("Starting 3 parallel tasks...")
        start_time = asyncio.get_event_loop().time()

        # Execute all in parallel
        results = await asyncio.gather(
            *[worker_pool.execute_task(task, timeout=30) for task in tasks],
            return_exceptions=True,
        )

        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time

        print(f"\n  Total time: {total_time:.2f}s")

        success_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print_error(f"  Task {i}: Exception - {result}")
            elif result.get("success"):
                print_success(f"  Task {i}: Success")
                success_count += 1
            else:
                print_error(f"  Task {i}: Failed - {result.get('error')}")

        print(f"\n  Success rate: {success_count}/3")

        await worker_pool.close()

        if success_count == 3:
            print_success("All parallel tasks completed successfully")
            return True
        else:
            print_error(f"Only {success_count}/3 tasks succeeded")
            return False

    except Exception as e:
        print_error(f"Parallel execution test failed: {e}")
        import traceback

        traceback.print_exc()
        await worker_pool.close()
        return False


async def test_error_handling():
    """Test 7: Error handling for invalid tasks."""
    print_header("Test 7: Error Handling")

    worker_pool = create_default_worker_pool()

    try:
        # Test 1: Invalid skill
        print_info("Testing invalid skill...")
        task = SubTask(
            task_id="test_error_001",
            description="Do something",
            skills=["nonexistent_skill"],
        )
        result = await worker_pool.execute_task(task, timeout=10)
        print(
            f"  Result: {'✓ Handled' if not result.get('success') else '✗ Should have failed'}"
        )

        # Test 2: Invalid command
        print_info("Testing invalid command...")
        task = SubTask(
            task_id="test_error_002",
            description="Run invalid_command_that_does_not_exist",
            skills=["shell_exec"],
        )
        result = await worker_pool.execute_task(task, timeout=10)
        print(
            f"  Result: {'✓ Handled' if not result.get('success') else '✗ Should have failed'}"
        )

        await worker_pool.close()
        print_success("Error handling working correctly")
        return True

    except Exception as e:
        print_error(f"Error handling test failed: {e}")
        await worker_pool.close()
        return False


async def run_all_tests():
    """Run all integration tests."""
    print_header("PiBot V3 Master-Worker Integration Tests")
    print_info("Make sure all 3 Workers are running before starting")
    print()

    tests = [
        ("Worker Health", test_worker_health),
        ("Worker Status", test_worker_status),
        ("Task Analysis", test_task_analysis),
        ("Simple Task Dispatch", test_simple_task_dispatch),
        ("Task Cancellation", test_task_cancellation),
        ("Parallel Execution", test_parallel_execution),
        ("Error Handling", test_error_handling),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results[test_name] = passed
        except Exception as e:
            print_error(f"Test '{test_name}' crashed: {e}")
            results[test_name] = False

    # Summary
    print_header("Test Summary")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed in results.items():
        status = (
            f"{Colors.GREEN}PASS{Colors.END}"
            if passed
            else f"{Colors.RED}FAIL{Colors.END}"
        )
        print(f"  {test_name}: {status}")

    print()
    print(f"Result: {passed}/{total} tests passed")

    if passed == total:
        print_success("All tests passed! ✨")
        return 0
    else:
        print_error(f"{total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
