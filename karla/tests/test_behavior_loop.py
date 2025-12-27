"""Behavior loop tests for karla - inspired by Ralph Wiggum technique.

This module implements iterative behavior loops for testing karla's tool execution.
The pattern is similar to ralph-wiggum: run a sequence of operations repeatedly
until a completion condition is met, verifying behavior across iterations.

The behavior loop tests are designed to:
1. Test stateful operations across multiple iterations
2. Verify tool interactions in complex scenarios
3. Test error recovery and retry behavior
4. Simulate agent-like iterative workflows

Run with: pytest tests/test_behavior_loop.py -v
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import pytest

from karla import ToolContext, ToolExecutor, ToolResult, create_default_registry
from karla.tools import TodoStore, TodoWriteTool


class LoopStatus(Enum):
    """Status of a behavior loop."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class LoopState:
    """State tracked across loop iterations."""
    iteration: int = 0
    max_iterations: int = 10
    status: LoopStatus = LoopStatus.RUNNING
    results: list[ToolResult] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    completion_promise: str | None = None


class BehaviorLoop:
    """A behavior loop runner for testing iterative tool execution.

    Inspired by the Ralph Wiggum technique: run operations in a loop until
    completion criteria are met, with full state tracking.
    """

    def __init__(
        self,
        executor: ToolExecutor,
        max_iterations: int = 10,
        completion_promise: str | None = None,
    ):
        self.executor = executor
        self.state = LoopState(
            max_iterations=max_iterations,
            completion_promise=completion_promise,
        )

    async def run_step(
        self,
        step_func: Callable[[LoopState, ToolExecutor], tuple[str, dict[str, Any]]],
        check_completion: Callable[[LoopState, ToolResult], bool] | None = None,
    ) -> LoopState:
        """Run a single step of the behavior loop.

        Args:
            step_func: Function that returns (tool_name, tool_args) based on state
            check_completion: Optional function to check if loop should complete

        Returns:
            Updated loop state
        """
        if self.state.status != LoopStatus.RUNNING:
            return self.state

        if self.state.iteration >= self.state.max_iterations:
            self.state.status = LoopStatus.MAX_ITERATIONS
            return self.state

        self.state.iteration += 1

        # Get the tool call for this step
        tool_name, tool_args = step_func(self.state, self.executor)

        # Execute the tool
        result = await self.executor.execute(tool_name, tool_args)
        self.state.results.append(result)

        # Check completion
        if check_completion and check_completion(self.state, result):
            self.state.status = LoopStatus.COMPLETED

        # Check for promise in result
        if self.state.completion_promise and self.state.completion_promise in result.output:
            self.state.status = LoopStatus.COMPLETED

        return self.state

    async def run_loop(
        self,
        step_func: Callable[[LoopState, ToolExecutor], tuple[str, dict[str, Any]]],
        check_completion: Callable[[LoopState, ToolResult], bool] | None = None,
    ) -> LoopState:
        """Run the complete behavior loop until completion or max iterations.

        Args:
            step_func: Function that returns (tool_name, tool_args) based on state
            check_completion: Optional function to check if loop should complete

        Returns:
            Final loop state
        """
        while self.state.status == LoopStatus.RUNNING:
            await self.run_step(step_func, check_completion)

        return self.state


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for behavior loop tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some initial files for iteration tests
        project_dir = Path(tmpdir)

        # Counter file for testing iterative modifications
        (project_dir / "counter.txt").write_text("0")

        # Log file for tracking iterations
        (project_dir / "log.txt").write_text("")

        # Data file for accumulation tests
        (project_dir / "data.json").write_text('{"items": []}')

        yield tmpdir


@pytest.fixture
def executor(temp_workspace):
    """Create a tool executor for the workspace."""
    registry = create_default_registry(temp_workspace)
    return ToolExecutor(registry, temp_workspace)


class TestBasicBehaviorLoop:
    """Test basic behavior loop functionality."""

    def test_simple_iteration_loop(self, executor, temp_workspace):
        """Test a simple loop that increments a counter."""
        counter_path = str(Path(temp_workspace) / "counter.txt")

        def increment_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Increment the counter in the file."""
            # Read current value from last result or start at 0
            if state.results:
                try:
                    current = int(state.context.get("counter", 0))
                except (ValueError, KeyError):
                    current = 0
            else:
                current = 0

            new_value = current + 1
            state.context["counter"] = new_value

            return "Write", {
                "file_path": counter_path,
                "content": str(new_value),
            }

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return state.context.get("counter", 0) >= 5

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(increment_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert state.iteration == 5
        assert state.context["counter"] == 5

        # Verify the file has the final value
        assert Path(counter_path).read_text() == "5"

    def test_read_modify_loop(self, executor, temp_workspace):
        """Test a loop that reads and modifies a file."""
        data_path = str(Path(temp_workspace) / "items.txt")
        Path(data_path).write_text("item-0")

        iteration_count = [0]

        def append_item_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Append a new item to the file."""
            iteration_count[0] += 1
            items = [f"item-{i}" for i in range(iteration_count[0] + 1)]
            return "Write", {
                "file_path": data_path,
                "content": "\n".join(items),
            }

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return iteration_count[0] >= 3

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(append_item_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert state.iteration == 3

        # Verify file has all items
        content = Path(data_path).read_text()
        assert "item-0" in content
        assert "item-1" in content
        assert "item-2" in content
        assert "item-3" in content

    def test_max_iterations_reached(self, executor, temp_workspace):
        """Test that loop stops at max iterations."""
        def infinite_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            return "Bash", {"command": "echo iteration"}

        loop = BehaviorLoop(executor, max_iterations=3)
        state = asyncio.run(loop.run_loop(infinite_step))

        assert state.status == LoopStatus.MAX_ITERATIONS
        assert state.iteration == 3


class TestComplexBehaviorLoops:
    """Test complex behavior loop scenarios."""

    def test_search_and_modify_loop(self, executor, temp_workspace):
        """Test a loop that searches for patterns and modifies files."""
        # Create some files with TODO comments
        src_dir = Path(temp_workspace) / "src"
        src_dir.mkdir()

        (src_dir / "file1.py").write_text("""
def func1():
    # TODO: Implement this
    pass
""")
        (src_dir / "file2.py").write_text("""
def func2():
    # TODO: Add error handling
    pass
""")

        files_fixed = []

        def fix_todo_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Find and fix TODO comments."""
            if not state.results:
                # First iteration: search for TODOs
                return "Grep", {
                    "pattern": "# TODO:",
                    "output_mode": "content",
                }

            last_result = state.results[-1]

            # If last was a grep, pick a file to fix
            if "TODO" in last_result.output and not files_fixed:
                # Find file1.py
                files_fixed.append("file1")
                return "Edit", {
                    "file_path": str(src_dir / "file1.py"),
                    "old_string": "# TODO: Implement this",
                    "new_string": "# DONE: Implemented",
                }
            elif len(files_fixed) == 1:
                # Fix file2.py
                files_fixed.append("file2")
                return "Edit", {
                    "file_path": str(src_dir / "file2.py"),
                    "old_string": "# TODO: Add error handling",
                    "new_string": "# DONE: Added error handling",
                }
            else:
                # Verify no more TODOs
                return "Grep", {
                    "pattern": "# TODO:",
                    "output_mode": "content",
                }

        def check_done(state: LoopState, result: ToolResult) -> bool:
            # Done when grep finds no TODOs after fixing both files
            if len(files_fixed) >= 2 and "No matches" in result.output:
                return True
            return False

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(fix_todo_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert len(files_fixed) == 2

        # Verify files were modified
        assert "DONE: Implemented" in (src_dir / "file1.py").read_text()
        assert "DONE: Added error handling" in (src_dir / "file2.py").read_text()

    def test_error_recovery_loop(self, executor, temp_workspace):
        """Test a loop that handles errors and retries."""
        target_file = Path(temp_workspace) / "target.txt"
        attempts = [0]

        def retry_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Try to read a file, create it if missing."""
            attempts[0] += 1

            if state.results and state.results[-1].is_error:
                # Last attempt failed, create the file
                return "Write", {
                    "file_path": str(target_file),
                    "content": "Created after retry!",
                }
            else:
                # Try to read the file
                return "Read", {"file_path": str(target_file)}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return not result.is_error and "Created after retry" in result.output

        loop = BehaviorLoop(executor, max_iterations=5)
        state = asyncio.run(loop.run_loop(retry_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        # Should have: failed read -> write -> successful read
        assert attempts[0] == 3
        assert target_file.read_text() == "Created after retry!"


class TestCompletionPromise:
    """Test completion promise detection (like ralph-wiggum <promise> tags)."""

    def test_promise_completion(self, executor, temp_workspace):
        """Test loop completes when promise text is found."""
        result_file = Path(temp_workspace) / "result.txt"
        iteration = [0]

        def step_with_promise(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            iteration[0] += 1
            if iteration[0] < 3:
                return "Write", {
                    "file_path": str(result_file),
                    "content": f"Working... iteration {iteration[0]}",
                }
            else:
                return "Bash", {
                    "command": "echo 'TASK_COMPLETE: All work finished'",
                }

        loop = BehaviorLoop(
            executor,
            max_iterations=10,
            completion_promise="TASK_COMPLETE",
        )
        state = asyncio.run(loop.run_loop(step_with_promise))

        assert state.status == LoopStatus.COMPLETED
        assert iteration[0] == 3

    def test_promise_not_found(self, executor, temp_workspace):
        """Test loop continues when promise is not found."""
        def step_without_promise(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            return "Bash", {"command": "echo 'Still working...'"}

        loop = BehaviorLoop(
            executor,
            max_iterations=3,
            completion_promise="NEVER_APPEARS",
        )
        state = asyncio.run(loop.run_loop(step_without_promise))

        # Should hit max iterations since promise never appears
        assert state.status == LoopStatus.MAX_ITERATIONS
        assert state.iteration == 3


class TestStatefulBehaviorLoops:
    """Test loops with complex state management."""

    def test_accumulating_state_loop(self, executor, temp_workspace):
        """Test a loop that accumulates state across iterations."""
        log_path = Path(temp_workspace) / "build_log.txt"
        log_path.write_text("")

        def build_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Simulate build steps."""
            steps = ["compile", "link", "test", "package"]
            # iteration is 1-indexed after increment in run_step, so use iteration-1
            step_idx = state.iteration - 1

            if step_idx < len(steps):
                step_name = steps[step_idx]
                state.context.setdefault("completed_steps", []).append(step_name)

                # Append to log
                current_log = log_path.read_text()
                new_log = current_log + f"Step {step_idx + 1}: {step_name}\n"

                return "Write", {
                    "file_path": str(log_path),
                    "content": new_log,
                }
            else:
                # All done
                return "Bash", {"command": "echo BUILD_COMPLETE"}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            completed = state.context.get("completed_steps", [])
            return len(completed) >= 4

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(build_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert state.context["completed_steps"] == ["compile", "link", "test", "package"]

        # Verify log file
        log_content = log_path.read_text()
        assert "Step 1: compile" in log_content
        assert "Step 4: package" in log_content

    def test_conditional_branching_loop(self, executor, temp_workspace):
        """Test a loop with conditional logic based on state."""
        config_path = Path(temp_workspace) / "config.ini"
        config_path.write_text("[settings]\nmode=development")

        def conditional_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Different behavior based on config."""
            if not state.context.get("config_read"):
                # First: read config
                state.context["config_read"] = True
                return "Read", {"file_path": str(config_path)}

            if not state.context.get("mode_checked"):
                # Check mode from last result
                state.context["mode_checked"] = True
                last_output = state.results[-1].output if state.results else ""

                if "development" in last_output:
                    state.context["mode"] = "development"
                    return "Write", {
                        "file_path": str(config_path),
                        "content": "[settings]\nmode=production",
                    }
                else:
                    state.context["mode"] = "production"
                    return "Bash", {"command": "echo 'Already in production'"}

            # Final verification
            return "Read", {"file_path": str(config_path)}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return (
                state.context.get("mode_checked") and
                state.iteration >= 3
            )

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(conditional_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert state.context["mode"] == "development"

        # Config should now be production
        assert "production" in config_path.read_text()


class TestTodoIntegrationLoop:
    """Test behavior loops with todo list integration."""

    def test_todo_workflow_loop(self, executor, temp_workspace):
        """Test a loop that manages todos across iterations."""
        store = TodoStore()
        todo_tool = TodoWriteTool(store)
        tool_context = ToolContext(working_dir=temp_workspace)

        tasks = [
            "Create project structure",
            "Write main module",
            "Add tests",
        ]

        def todo_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Work through todo list."""
            # Use iteration count to track progress (1-indexed)
            idx = state.iteration

            if idx == 1:
                # Initial: create all todos as pending
                return "TodoWrite", {
                    "todos": [
                        {"content": t, "status": "pending", "activeForm": f"Working on {t}"}
                        for t in tasks
                    ]
                }
            elif idx <= len(tasks) + 1:
                # Update status: complete previous ones, current one in progress
                completed_count = idx - 1
                todos = []
                for i, t in enumerate(tasks):
                    if i < completed_count:
                        status = "completed"
                    elif i == completed_count and completed_count < len(tasks):
                        status = "in_progress"
                    else:
                        status = "pending"
                    todos.append({
                        "content": t,
                        "status": status,
                        "activeForm": f"Working on {t}",
                    })
                return "TodoWrite", {"todos": todos}
            else:
                # All done - mark everything completed
                todos = [
                    {"content": t, "status": "completed", "activeForm": f"Working on {t}"}
                    for t in tasks
                ]
                return "TodoWrite", {"todos": todos}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            # Done after we've completed all tasks (iteration > len(tasks) + 1)
            return state.iteration > len(tasks) + 1

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(todo_step, check_done))

        assert state.status == LoopStatus.COMPLETED

        # Verify all todos are completed
        final_result = state.results[-1]
        assert "3 completed" in final_result.output


class TestAgentSimulationLoop:
    """Test loops that simulate agent-like behavior."""

    def test_code_review_simulation(self, executor, temp_workspace):
        """Simulate an agent doing code review."""
        # Create a file with issues
        code_path = Path(temp_workspace) / "review_target.py"
        code_path.write_text('''def calculate(x,y):
    result=x+y
    return result
''')

        issues_found = []
        fixes_applied = []

        def review_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Simulate code review and fixes."""
            if not state.context.get("code_read"):
                state.context["code_read"] = True
                return "Read", {"file_path": str(code_path)}

            if not issues_found:
                # Analyze and find issues
                issues_found.append("missing_spaces")
                return "Edit", {
                    "file_path": str(code_path),
                    "old_string": "def calculate(x,y):",
                    "new_string": "def calculate(x, y):",
                }

            if len(fixes_applied) == 0:
                fixes_applied.append("spaces_in_def")
                return "Edit", {
                    "file_path": str(code_path),
                    "old_string": "result=x+y",
                    "new_string": "result = x + y",
                }

            if len(fixes_applied) == 1:
                fixes_applied.append("spaces_in_expr")
                # Final read to verify
                return "Read", {"file_path": str(code_path)}

            return "Bash", {"command": "echo REVIEW_COMPLETE"}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return "REVIEW_COMPLETE" in result.output

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(review_step, check_done))

        assert state.status == LoopStatus.COMPLETED
        assert len(fixes_applied) == 2

        # Verify the code is properly formatted
        final_code = code_path.read_text()
        assert "def calculate(x, y):" in final_code
        assert "result = x + y" in final_code

    def test_file_organization_simulation(self, executor, temp_workspace):
        """Simulate organizing files into directories."""
        # Create scattered files
        files_to_organize = ["app.py", "test_app.py", "config.yaml", "README.md"]
        for f in files_to_organize:
            (Path(temp_workspace) / f).write_text(f"Content of {f}")

        organized = []

        def organize_step(state: LoopState, exec: ToolExecutor) -> tuple[str, dict]:
            """Organize files by type."""
            if not organized:
                # Create src directory and move app.py
                organized.append("src")
                return "Bash", {
                    "command": f"mkdir -p {temp_workspace}/src && mv {temp_workspace}/app.py {temp_workspace}/src/",
                }

            if len(organized) == 1:
                # Create tests directory and move test file
                organized.append("tests")
                return "Bash", {
                    "command": f"mkdir -p {temp_workspace}/tests && mv {temp_workspace}/test_app.py {temp_workspace}/tests/",
                }

            if len(organized) == 2:
                # Verify structure
                organized.append("verified")
                return "Glob", {"pattern": "**/*.py"}

            return "Bash", {"command": "echo ORGANIZED"}

        def check_done(state: LoopState, result: ToolResult) -> bool:
            return "ORGANIZED" in result.output

        loop = BehaviorLoop(executor, max_iterations=10)
        state = asyncio.run(loop.run_loop(organize_step, check_done))

        assert state.status == LoopStatus.COMPLETED

        # Verify files are in correct locations
        assert (Path(temp_workspace) / "src" / "app.py").exists()
        assert (Path(temp_workspace) / "tests" / "test_app.py").exists()
