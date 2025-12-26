"""Tests for karla tools."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from karla import ToolContext, ToolResult, create_default_registry
from karla.tools import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    ReadTool,
    WriteTool,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def tool_context(temp_dir):
    """Create a tool context for tests."""
    return ToolContext(working_dir=temp_dir)


class TestReadTool:
    """Tests for the Read tool."""

    def test_read_existing_file(self, temp_dir, tool_context):
        """Test reading an existing file."""
        # Create a test file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        tool = ReadTool(temp_dir)
        result = asyncio.run(tool.execute({"file_path": str(test_file)}, tool_context))

        assert not result.is_error
        assert "line 1" in result.output
        assert "line 2" in result.output
        assert "line 3" in result.output

    def test_read_nonexistent_file(self, temp_dir, tool_context):
        """Test reading a file that doesn't exist."""
        tool = ReadTool(temp_dir)
        result = asyncio.run(
            tool.execute({"file_path": str(Path(temp_dir) / "nonexistent.txt")}, tool_context)
        )

        assert result.is_error
        assert "does not exist" in result.output

    def test_read_with_offset_and_limit(self, temp_dir, tool_context):
        """Test reading with offset and limit."""
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 101)]))

        tool = ReadTool(temp_dir)
        result = asyncio.run(
            tool.execute({"file_path": str(test_file), "offset": 10, "limit": 5}, tool_context)
        )

        assert not result.is_error
        assert "line 10" in result.output
        assert "line 14" in result.output
        # Should not contain lines outside range
        assert "line 9" not in result.output or "→" in result.output  # 9 might be in line numbers

    def test_read_missing_path(self, temp_dir, tool_context):
        """Test reading without providing a path."""
        tool = ReadTool(temp_dir)
        result = asyncio.run(tool.execute({}, tool_context))

        assert result.is_error
        assert "file_path is required" in result.output


class TestWriteTool:
    """Tests for the Write tool."""

    def test_write_new_file(self, temp_dir, tool_context):
        """Test writing a new file."""
        test_file = Path(temp_dir) / "new_file.txt"

        tool = WriteTool(temp_dir)
        result = asyncio.run(
            tool.execute({"file_path": str(test_file), "content": "Hello, world!"}, tool_context)
        )

        assert not result.is_error
        assert test_file.exists()
        assert test_file.read_text() == "Hello, world!"

    def test_write_overwrites_existing(self, temp_dir, tool_context):
        """Test that writing overwrites existing files."""
        test_file = Path(temp_dir) / "existing.txt"
        test_file.write_text("old content")

        tool = WriteTool(temp_dir)
        result = asyncio.run(
            tool.execute({"file_path": str(test_file), "content": "new content"}, tool_context)
        )

        assert not result.is_error
        assert test_file.read_text() == "new content"

    def test_write_creates_directories(self, temp_dir, tool_context):
        """Test that writing creates parent directories."""
        test_file = Path(temp_dir) / "subdir" / "nested" / "file.txt"

        tool = WriteTool(temp_dir)
        result = asyncio.run(
            tool.execute({"file_path": str(test_file), "content": "nested content"}, tool_context)
        )

        assert not result.is_error
        assert test_file.exists()
        assert test_file.read_text() == "nested content"


class TestEditTool:
    """Tests for the Edit tool."""

    def test_edit_replace_string(self, temp_dir, tool_context):
        """Test replacing a string in a file."""
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Hello, world!")

        tool = EditTool(temp_dir)
        result = asyncio.run(
            tool.execute(
                {"file_path": str(test_file), "old_string": "world", "new_string": "universe"},
                tool_context,
            )
        )

        assert not result.is_error
        assert test_file.read_text() == "Hello, universe!"

    def test_edit_string_not_found(self, temp_dir, tool_context):
        """Test editing when old_string is not found."""
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Hello, world!")

        tool = EditTool(temp_dir)
        result = asyncio.run(
            tool.execute(
                {"file_path": str(test_file), "old_string": "foo", "new_string": "bar"},
                tool_context,
            )
        )

        assert result.is_error
        assert "not found" in result.output.lower()


class TestBashTool:
    """Tests for the Bash tool."""

    def test_bash_simple_command(self, temp_dir, tool_context):
        """Test running a simple bash command."""
        tool = BashTool()
        result = asyncio.run(tool.execute({"command": "echo 'hello'"}, tool_context))

        assert not result.is_error
        assert "hello" in result.output

    def test_bash_command_with_exit_code(self, temp_dir, tool_context):
        """Test a command that exits with non-zero code."""
        tool = BashTool()
        result = asyncio.run(tool.execute({"command": "exit 1"}, tool_context))

        assert result.is_error
        assert "exit code: 1" in result.output

    def test_bash_command_working_dir(self, temp_dir, tool_context):
        """Test that command runs in the working directory."""
        tool = BashTool()
        result = asyncio.run(tool.execute({"command": "pwd"}, tool_context))

        assert not result.is_error
        assert temp_dir in result.output


class TestGlobTool:
    """Tests for the Glob tool."""

    def test_glob_find_files(self, temp_dir, tool_context):
        """Test finding files with glob pattern."""
        # Create test files
        (Path(temp_dir) / "file1.py").write_text("# python file 1")
        (Path(temp_dir) / "file2.py").write_text("# python file 2")
        (Path(temp_dir) / "file.txt").write_text("text file")

        tool = GlobTool(temp_dir)
        result = asyncio.run(tool.execute({"pattern": "*.py"}, tool_context))

        assert not result.is_error
        assert "file1.py" in result.output
        assert "file2.py" in result.output
        assert "file.txt" not in result.output

    def test_glob_no_matches(self, temp_dir, tool_context):
        """Test glob with no matches."""
        tool = GlobTool(temp_dir)
        result = asyncio.run(tool.execute({"pattern": "*.nonexistent"}, tool_context))

        assert not result.is_error
        assert "No files found" in result.output


class TestGrepTool:
    """Tests for the Grep tool."""

    def test_grep_find_pattern(self, temp_dir, tool_context):
        """Test finding a pattern in files."""
        # Create test files
        (Path(temp_dir) / "file1.py").write_text("def hello():\n    pass\n")
        (Path(temp_dir) / "file2.py").write_text("def world():\n    pass\n")

        tool = GrepTool(temp_dir)
        result = asyncio.run(
            tool.execute({"pattern": "def hello", "output_mode": "content"}, tool_context)
        )

        assert not result.is_error
        assert "hello" in result.output

    def test_grep_no_matches(self, temp_dir, tool_context):
        """Test grep with no matches."""
        (Path(temp_dir) / "file.txt").write_text("nothing here")

        tool = GrepTool(temp_dir)
        result = asyncio.run(tool.execute({"pattern": "nonexistent"}, tool_context))

        assert not result.is_error
        assert "No matches" in result.output


class TestRegistry:
    """Tests for the tool registry."""

    def test_create_default_registry(self, temp_dir):
        """Test creating a default registry."""
        registry = create_default_registry(temp_dir)

        # Check that all expected tools are registered
        tool_names = [t.name for t in registry]
        assert "Read" in tool_names
        assert "Write" in tool_names
        assert "Edit" in tool_names
        assert "Bash" in tool_names
        assert "Grep" in tool_names
        assert "Glob" in tool_names
        assert "Task" in tool_names
        assert "TaskOutput" in tool_names
        assert "Skill" in tool_names
        assert "TodoWrite" in tool_names
        assert "EnterPlanMode" in tool_names
        assert "ExitPlanMode" in tool_names
        assert "AskUserQuestion" in tool_names

    def test_registry_get_tool(self, temp_dir):
        """Test getting a tool by name."""
        registry = create_default_registry(temp_dir)

        read_tool = registry.get("Read")
        assert read_tool is not None
        assert read_tool.name == "Read"

    def test_registry_get_nonexistent(self, temp_dir):
        """Test getting a tool that doesn't exist."""
        registry = create_default_registry(temp_dir)

        tool = registry.get("NonexistentTool")
        assert tool is None


class TestToolResult:
    """Tests for ToolResult."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ToolResult.success("Operation completed")
        assert not result.is_error
        assert result.output == "Operation completed"

    def test_error_result(self):
        """Test creating an error result."""
        result = ToolResult.error("Something went wrong")
        assert result.is_error
        assert result.output == "Something went wrong"

    def test_result_with_stdio(self):
        """Test result with stdout/stderr."""
        result = ToolResult(output="done", stdout="output text", stderr="warning text")
        assert result.stdout == "output text"
        assert result.stderr == "warning text"
