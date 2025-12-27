"""End-to-end tests for karla coding agent.

These tests verify multi-step workflows, tool chaining, and complex scenarios
that mimic real-world agent behavior. They test the tools at the integration
level without requiring a Letta server.

Run with: pytest tests/test_e2e.py -v
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from karla import ToolContext, ToolExecutor, ToolResult, create_default_registry
from karla.tools import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    ReadTool,
    TodoStore,
    TodoWriteTool,
    WriteTool,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for E2E tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a realistic project structure
        project_dir = Path(tmpdir)

        # src directory
        src_dir = project_dir / "src"
        src_dir.mkdir()

        # Create some Python files
        (src_dir / "main.py").write_text('''#!/usr/bin/env python3
"""Main application entry point."""

import logging
from config import load_config
from server import Server

logger = logging.getLogger(__name__)


def main():
    """Start the application."""
    config = load_config()
    server = Server(config)
    logger.info("Starting server on port %d", config.port)
    server.run()


if __name__ == "__main__":
    main()
''')

        (src_dir / "config.py").write_text('''"""Configuration management."""

from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration."""

    host: str = "localhost"
    port: int = 8080
    debug: bool = False


def load_config() -> Config:
    """Load configuration from environment."""
    import os
    return Config(
        host=os.environ.get("HOST", "localhost"),
        port=int(os.environ.get("PORT", "8080")),
        debug=os.environ.get("DEBUG", "").lower() == "true",
    )
''')

        (src_dir / "server.py").write_text('''"""Server implementation."""

import logging

logger = logging.getLogger(__name__)


class Server:
    """HTTP server."""

    def __init__(self, config):
        self.config = config
        self._running = False

    def run(self):
        """Start the server."""
        self._running = True
        logger.info("Server running at %s:%d", self.config.host, self.config.port)

    def stop(self):
        """Stop the server."""
        self._running = False
        logger.info("Server stopped")
''')

        # tests directory
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()

        (tests_dir / "test_config.py").write_text('''"""Tests for configuration."""

import pytest
from src.config import Config, load_config


def test_default_config():
    config = Config()
    assert config.host == "localhost"
    assert config.port == 8080
    assert config.debug is False


def test_load_config(monkeypatch):
    monkeypatch.setenv("PORT", "9000")
    config = load_config()
    assert config.port == 9000
''')

        # README
        (project_dir / "README.md").write_text('''# Test Project

A sample project for E2E testing.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python src/main.py
```
''')

        yield tmpdir


@pytest.fixture
def tool_context(temp_workspace):
    """Create a tool context for the workspace."""
    return ToolContext(working_dir=temp_workspace)


@pytest.fixture
def registry(temp_workspace):
    """Create a tool registry for the workspace."""
    return create_default_registry(temp_workspace)


@pytest.fixture
def executor(registry, temp_workspace):
    """Create a tool executor."""
    return ToolExecutor(registry, temp_workspace)


class TestMultiStepWorkflows:
    """Test complex multi-step workflows that mimic real agent behavior."""

    def test_explore_modify_verify(self, temp_workspace, tool_context):
        """Test: Explore codebase -> Modify file -> Verify change.

        This mimics the common pattern:
        1. Search for a file
        2. Read it to understand context
        3. Make a modification
        4. Verify the change was applied
        """
        # Step 1: Find Python files
        glob_tool = GlobTool(temp_workspace)
        result = asyncio.run(
            glob_tool.execute({"pattern": "**/*.py"}, tool_context)
        )
        assert not result.is_error
        assert "main.py" in result.output
        assert "config.py" in result.output

        # Step 2: Search for where config is used
        grep_tool = GrepTool(temp_workspace)
        result = asyncio.run(
            grep_tool.execute(
                {"pattern": "load_config", "output_mode": "content"},
                tool_context
            )
        )
        assert not result.is_error
        assert "main.py" in result.output or "config.py" in result.output

        # Step 3: Read the config file
        read_tool = ReadTool(temp_workspace)
        config_path = str(Path(temp_workspace) / "src" / "config.py")
        result = asyncio.run(
            read_tool.execute({"file_path": config_path}, tool_context)
        )
        assert not result.is_error
        assert "port: int = 8080" in result.output

        # Step 4: Modify the default port
        edit_tool = EditTool(temp_workspace)
        result = asyncio.run(
            edit_tool.execute({
                "file_path": config_path,
                "old_string": "port: int = 8080",
                "new_string": "port: int = 3000",
            }, tool_context)
        )
        assert not result.is_error

        # Step 5: Verify the change
        result = asyncio.run(
            read_tool.execute({"file_path": config_path}, tool_context)
        )
        assert not result.is_error
        assert "port: int = 3000" in result.output
        assert "port: int = 8080" not in result.output

    def test_find_pattern_across_files(self, temp_workspace, tool_context):
        """Test finding and analyzing a pattern across multiple files."""
        grep_tool = GrepTool(temp_workspace)
        read_tool = ReadTool(temp_workspace)

        # Step 1: Find all logging usages
        result = asyncio.run(
            grep_tool.execute(
                {"pattern": "logger\\.", "output_mode": "files_with_matches"},
                tool_context
            )
        )
        assert not result.is_error

        # Step 2: Read each file with logging to analyze
        files_with_logging = []
        for line in result.output.split("\n"):
            if line.strip() and line.endswith(".py"):
                files_with_logging.append(line.strip())

        # Should have found logging in multiple files
        assert len(files_with_logging) >= 2

        # Step 3: Read and verify logging usage in main.py
        main_path = str(Path(temp_workspace) / "src" / "main.py")
        result = asyncio.run(
            read_tool.execute({"file_path": main_path}, tool_context)
        )
        assert not result.is_error
        assert "logger.info" in result.output

    def test_create_new_file_and_reference(self, temp_workspace, tool_context):
        """Test creating a new file and updating another to reference it."""
        write_tool = WriteTool(temp_workspace)
        edit_tool = EditTool(temp_workspace)
        read_tool = ReadTool(temp_workspace)

        # Step 1: Create a new utility module
        utils_path = str(Path(temp_workspace) / "src" / "utils.py")
        utils_content = '''"""Utility functions."""


def format_port(port: int) -> str:
    """Format port number for display."""
    return f":{port}"


def validate_port(port: int) -> bool:
    """Validate that port is in valid range."""
    return 1 <= port <= 65535
'''
        result = asyncio.run(
            write_tool.execute(
                {"file_path": utils_path, "content": utils_content},
                tool_context
            )
        )
        assert not result.is_error

        # Step 2: Update config.py to import and use the utility
        config_path = str(Path(temp_workspace) / "src" / "config.py")
        result = asyncio.run(
            edit_tool.execute({
                "file_path": config_path,
                "old_string": '"""Configuration management."""',
                "new_string": '"""Configuration management."""\n\nfrom utils import validate_port',
            }, tool_context)
        )
        assert not result.is_error

        # Step 3: Verify both files exist and have correct content
        result = asyncio.run(
            read_tool.execute({"file_path": utils_path}, tool_context)
        )
        assert not result.is_error
        assert "validate_port" in result.output

        result = asyncio.run(
            read_tool.execute({"file_path": config_path}, tool_context)
        )
        assert not result.is_error
        assert "from utils import validate_port" in result.output

    def test_run_and_capture_command_output(self, temp_workspace, tool_context):
        """Test running a command and using its output for further operations."""
        bash_tool = BashTool()
        read_tool = ReadTool(temp_workspace)

        # Step 1: List Python files and capture output
        result = asyncio.run(
            bash_tool.execute(
                {"command": f"find {temp_workspace} -name '*.py' | wc -l"},
                tool_context
            )
        )
        assert not result.is_error
        count = int(result.output.strip())
        assert count >= 4  # main.py, config.py, server.py, test_config.py

        # Step 2: Get Python version
        result = asyncio.run(
            bash_tool.execute({"command": "python3 --version"}, tool_context)
        )
        assert not result.is_error
        assert "Python" in result.output

        # Step 3: Check syntax of Python files
        main_path = str(Path(temp_workspace) / "src" / "main.py")
        result = asyncio.run(
            bash_tool.execute(
                {"command": f"python3 -m py_compile {main_path}"},
                tool_context
            )
        )
        assert not result.is_error


class TestToolChaining:
    """Test scenarios where tools must be used in sequence with dependencies."""

    def test_read_modify_verify_chain(self, executor, temp_workspace):
        """Test read -> edit -> read chain with executor."""
        config_path = str(Path(temp_workspace) / "src" / "config.py")

        # Chain: Read -> Edit -> Read (verify)
        result1 = asyncio.run(
            executor.execute("Read", {"file_path": config_path})
        )
        assert not result1.is_error
        assert "port: int = 8080" in result1.output

        result2 = asyncio.run(
            executor.execute("Edit", {
                "file_path": config_path,
                "old_string": "port: int = 8080",
                "new_string": "port: int = 9090",
            })
        )
        assert not result2.is_error

        result3 = asyncio.run(
            executor.execute("Read", {"file_path": config_path})
        )
        assert not result3.is_error
        assert "port: int = 9090" in result3.output

    def test_glob_grep_read_chain(self, executor, temp_workspace):
        """Test glob -> grep -> read chain for code discovery."""
        # Step 1: Find all Python files
        result1 = asyncio.run(
            executor.execute("Glob", {"pattern": "**/*.py"})
        )
        assert not result1.is_error

        # Step 2: Search for a specific pattern
        result2 = asyncio.run(
            executor.execute("Grep", {
                "pattern": "class Server",
                "output_mode": "content",
            })
        )
        assert not result2.is_error
        assert "Server" in result2.output

        # Step 3: Read the file containing the class
        server_path = str(Path(temp_workspace) / "src" / "server.py")
        result3 = asyncio.run(
            executor.execute("Read", {"file_path": server_path})
        )
        assert not result3.is_error
        assert "class Server" in result3.output
        assert "def run(self)" in result3.output

    def test_write_bash_verify_chain(self, executor, temp_workspace):
        """Test write -> bash -> read chain for script creation and execution."""
        script_path = str(Path(temp_workspace) / "hello.sh")

        # Step 1: Write a shell script
        result1 = asyncio.run(
            executor.execute("Write", {
                "file_path": script_path,
                "content": '#!/bin/bash\necho "Hello from karla test!"',
            })
        )
        assert not result1.is_error

        # Step 2: Make it executable and run
        result2 = asyncio.run(
            executor.execute("Bash", {
                "command": f"chmod +x {script_path} && {script_path}",
            })
        )
        assert not result2.is_error
        assert "Hello from karla test!" in result2.output

        # Step 3: Verify the file exists and has correct content
        result3 = asyncio.run(
            executor.execute("Read", {"file_path": script_path})
        )
        assert not result3.is_error
        assert "Hello from karla test" in result3.output


class TestTodoWorkflows:
    """Test todo list management in complex workflows."""

    def test_todo_planning_workflow(self, tool_context):
        """Test using todo list to plan and track a workflow."""
        store = TodoStore()
        todo_tool = TodoWriteTool(store)

        # Step 1: Create initial plan
        result = asyncio.run(
            todo_tool.execute({
                "todos": [
                    {"content": "Find all config files", "status": "pending", "activeForm": "Finding config files"},
                    {"content": "Update port numbers", "status": "pending", "activeForm": "Updating port numbers"},
                    {"content": "Verify changes", "status": "pending", "activeForm": "Verifying changes"},
                ]
            }, tool_context)
        )
        assert not result.is_error
        assert "3 pending" in result.output

        # Step 2: Start first task
        result = asyncio.run(
            todo_tool.execute({
                "todos": [
                    {"content": "Find all config files", "status": "in_progress", "activeForm": "Finding config files"},
                    {"content": "Update port numbers", "status": "pending", "activeForm": "Updating port numbers"},
                    {"content": "Verify changes", "status": "pending", "activeForm": "Verifying changes"},
                ]
            }, tool_context)
        )
        assert not result.is_error
        assert "1 in progress" in result.output

        # Step 3: Complete first, start second
        result = asyncio.run(
            todo_tool.execute({
                "todos": [
                    {"content": "Find all config files", "status": "completed", "activeForm": "Finding config files"},
                    {"content": "Update port numbers", "status": "in_progress", "activeForm": "Updating port numbers"},
                    {"content": "Verify changes", "status": "pending", "activeForm": "Verifying changes"},
                ]
            }, tool_context)
        )
        assert not result.is_error
        assert "1 completed" in result.output
        assert "1 in progress" in result.output

        # Step 4: Complete all
        result = asyncio.run(
            todo_tool.execute({
                "todos": [
                    {"content": "Find all config files", "status": "completed", "activeForm": "Finding config files"},
                    {"content": "Update port numbers", "status": "completed", "activeForm": "Updating port numbers"},
                    {"content": "Verify changes", "status": "completed", "activeForm": "Verifying changes"},
                ]
            }, tool_context)
        )
        assert not result.is_error
        assert "3 completed" in result.output
        assert "0 in progress" in result.output
        assert "0 pending" in result.output


class TestErrorRecovery:
    """Test error handling and recovery in workflows."""

    def test_handle_missing_file(self, executor, temp_workspace):
        """Test graceful handling of missing file errors."""
        # Try to read non-existent file
        result = asyncio.run(
            executor.execute("Read", {
                "file_path": str(Path(temp_workspace) / "nonexistent.py")
            })
        )
        assert result.is_error
        assert "does not exist" in result.output

        # Should be able to continue with valid operations
        result = asyncio.run(
            executor.execute("Glob", {"pattern": "**/*.py"})
        )
        assert not result.is_error

    def test_handle_edit_string_not_found(self, executor, temp_workspace):
        """Test handling edit when string not found."""
        config_path = str(Path(temp_workspace) / "src" / "config.py")

        result = asyncio.run(
            executor.execute("Edit", {
                "file_path": config_path,
                "old_string": "this string does not exist",
                "new_string": "replacement",
            })
        )
        assert result.is_error
        assert "not found" in result.output.lower()

    def test_handle_command_failure(self, executor, temp_workspace):
        """Test handling bash command failures."""
        result = asyncio.run(
            executor.execute("Bash", {"command": "exit 1"})
        )
        assert result.is_error
        assert "exit code: 1" in result.output

    def test_unknown_tool(self, executor):
        """Test handling of unknown tool name."""
        result = asyncio.run(
            executor.execute("NonexistentTool", {"arg": "value"})
        )
        assert result.is_error
        assert "Unknown tool" in result.output


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_refactoring_workflow(self, executor, temp_workspace):
        """Test a realistic refactoring workflow.

        Scenario: Rename a method across the codebase.
        """
        # Step 1: Find all usages of the method
        result = asyncio.run(
            executor.execute("Grep", {
                "pattern": "load_config",
                "output_mode": "files_with_matches",
            })
        )
        assert not result.is_error
        files_to_update = [f.strip() for f in result.output.split("\n") if f.strip()]

        # Step 2: Update each file
        for file_path in files_to_update:
            if not file_path.endswith(".py"):
                continue

            # Read current content
            result = asyncio.run(
                executor.execute("Read", {"file_path": file_path})
            )
            if result.is_error:
                continue

            # Check if it contains the function definition or just import
            if "def load_config" in result.output:
                # This is the definition - update it
                result = asyncio.run(
                    executor.execute("Edit", {
                        "file_path": file_path,
                        "old_string": "def load_config",
                        "new_string": "def get_config",
                    })
                )
                assert not result.is_error

        # Step 3: Verify the rename
        result = asyncio.run(
            executor.execute("Grep", {
                "pattern": "def get_config",
                "output_mode": "content",
            })
        )
        assert not result.is_error
        assert "get_config" in result.output

    def test_bug_investigation_workflow(self, executor, temp_workspace):
        """Test a bug investigation workflow.

        Scenario: Find where a specific configuration value is used.
        """
        # Step 1: Find the configuration definition
        result = asyncio.run(
            executor.execute("Grep", {
                "pattern": "port.*=.*8080",
                "output_mode": "content",
            })
        )
        assert not result.is_error

        # Step 2: Find all references to port
        result = asyncio.run(
            executor.execute("Grep", {
                "pattern": "\\.port",
                "output_mode": "content",
            })
        )
        assert not result.is_error
        # Should find config.port usage

        # Step 3: Read the main file to understand the flow
        main_path = str(Path(temp_workspace) / "src" / "main.py")
        result = asyncio.run(
            executor.execute("Read", {"file_path": main_path})
        )
        assert not result.is_error
        assert "config.port" in result.output

    def test_test_file_creation_workflow(self, executor, temp_workspace):
        """Test creating a test file for existing code."""
        # Step 1: Read the server module to understand what to test
        server_path = str(Path(temp_workspace) / "src" / "server.py")
        result = asyncio.run(
            executor.execute("Read", {"file_path": server_path})
        )
        assert not result.is_error

        # Step 2: Create a test file
        test_content = '''"""Tests for server module."""

import pytest
from src.server import Server
from src.config import Config


@pytest.fixture
def config():
    return Config(host="localhost", port=8080, debug=True)


@pytest.fixture
def server(config):
    return Server(config)


class TestServer:
    def test_server_creation(self, server, config):
        assert server.config == config
        assert server._running is False

    def test_server_run(self, server):
        server.run()
        assert server._running is True

    def test_server_stop(self, server):
        server.run()
        server.stop()
        assert server._running is False
'''
        test_path = str(Path(temp_workspace) / "tests" / "test_server.py")
        result = asyncio.run(
            executor.execute("Write", {
                "file_path": test_path,
                "content": test_content,
            })
        )
        assert not result.is_error

        # Step 3: Verify the test file was created correctly
        result = asyncio.run(
            executor.execute("Read", {"file_path": test_path})
        )
        assert not result.is_error
        assert "class TestServer" in result.output
        assert "def test_server_run" in result.output


class TestParallelOperations:
    """Test scenarios that could be run in parallel."""

    def test_multiple_file_reads(self, executor, temp_workspace):
        """Test reading multiple files that could be done in parallel."""
        files_to_read = [
            str(Path(temp_workspace) / "src" / "main.py"),
            str(Path(temp_workspace) / "src" / "config.py"),
            str(Path(temp_workspace) / "src" / "server.py"),
        ]

        # In a real agent, these would be parallel Task calls
        # Here we verify they can all complete successfully
        results = []
        for file_path in files_to_read:
            result = asyncio.run(
                executor.execute("Read", {"file_path": file_path})
            )
            results.append(result)

        # All should succeed
        for result in results:
            assert not result.is_error

        # Verify we got distinct content
        contents = [r.output for r in results]
        assert len(set(contents)) == 3  # All different

    def test_multiple_grep_patterns(self, executor, temp_workspace):
        """Test multiple grep patterns that could be run in parallel."""
        patterns = ["import", "def ", "class ", "logger"]

        results = []
        for pattern in patterns:
            result = asyncio.run(
                executor.execute("Grep", {
                    "pattern": pattern,
                    "output_mode": "files_with_matches",
                })
            )
            results.append(result)

        # All should succeed
        for result in results:
            assert not result.is_error


class TestRegistryCompleteness:
    """Test that all tools are properly registered and functional."""

    def test_all_tools_registered(self, registry):
        """Verify all expected tools are in the registry."""
        expected_tools = [
            "Read", "Write", "Edit",
            "Bash", "BashOutput", "KillBash",
            "Grep", "Glob",
            "EnterPlanMode", "ExitPlanMode",
            "TodoWrite",
            "Task", "TaskOutput",
            "Skill",
            "AskUserQuestion",
        ]

        registered_names = [tool.name for tool in registry]

        for expected in expected_tools:
            assert expected in registered_names, f"Missing tool: {expected}"

    def test_tool_schemas_valid(self, registry):
        """Verify all tool schemas are valid for OpenAI format."""
        for tool in registry:
            defn = tool.definition()
            schema = defn.to_openai_schema(strict=True)

            # Should have required structure
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema

            func = schema["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

            # Name should match tool name
            assert func["name"] == tool.name

    def test_tool_letta_sources_valid(self, registry):
        """Verify Letta source generation works for all tools."""
        import warnings

        sources = registry.to_letta_sources()

        assert len(sources) > 0

        for name, source in sources.items():
            # Should be valid Python syntax
            assert "def " in source
            assert "raise Exception" in source

            # Should compile without errors (suppress SyntaxWarning for docstrings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    compile(source, f"<{name}>", "exec")
            except SyntaxError as e:
                pytest.fail(f"Tool {name} generates invalid Python: {e}")
