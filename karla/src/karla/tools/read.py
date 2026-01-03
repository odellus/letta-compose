"""Read file tool - reads file contents with line numbering."""

import os
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

DEFAULT_LINE_LIMIT = 2000
MAX_LINE_LENGTH = 2000
BINARY_CHECK_SIZE = 8192
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class ReadTool(Tool):
    """Read file contents with line numbering."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "Read"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Read",
            description="""Reads a file from the local filesystem.

Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files)
- Any lines longer than 2000 characters will be truncated
- Results are returned with line numbers (1-indexed)
- You can call multiple tools in a single response to speculatively read multiple files.""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed, optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read (optional, default 2000)",
                    },
                },
                "required": ["file_path"],
            },
        )

    def _resolve_path(self, path: str) -> Path:
        """Resolve and validate a path."""
        requested = Path(path)
        if requested.is_absolute():
            full_path = requested
        else:
            full_path = self.working_dir / requested

        # Resolve to canonical path
        try:
            canonical = full_path.resolve()
        except OSError as e:
            raise ValueError(f"Cannot resolve path: {e}")

        # Security: ensure path is within working directory or /tmp (for testing)
        try:
            canonical.relative_to(self.working_dir)
        except ValueError:
            # Allow /tmp paths for testing
            if not str(canonical).startswith("/tmp/"):
                raise ValueError(f"Path is outside working directory: {path}")

        return canonical

    def _is_binary_file(self, path: Path) -> bool:
        """Check if a file appears to be binary."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(BINARY_CHECK_SIZE)
                if not chunk:
                    return False
                # Check for null bytes
                if b"\x00" in chunk:
                    return True
                # Try to decode as UTF-8
                try:
                    text = chunk.decode("utf-8")
                    # Check for replacement character (invalid UTF-8)
                    if "\ufffd" in text:
                        return True
                    # Count control characters
                    control_chars = sum(1 for c in text if ord(c) < 9 or (13 < ord(c) < 32))
                    return control_chars / len(text) > 0.3 if text else False
                except UnicodeDecodeError:
                    return True
        except OSError:
            return False

    def _format_with_line_numbers(
        self, content: str, offset: int = 0, limit: int = DEFAULT_LINE_LIMIT
    ) -> str:
        """Format content with line numbers."""
        lines = content.split("\n")
        total_lines = len(lines)

        # Apply offset and limit
        start_line = min(offset, len(lines))
        end_line = min(start_line + limit, len(lines))
        selected_lines = lines[start_line:end_line]

        # Format with line numbers
        formatted = []
        max_line_num = start_line + len(selected_lines)
        padding = len(str(max_line_num))
        lines_truncated = False

        for idx, line in enumerate(selected_lines):
            line_number = start_line + idx + 1  # 1-indexed
            # Truncate long lines
            if len(line) > MAX_LINE_LENGTH:
                line = line[:MAX_LINE_LENGTH] + "... [line truncated]"
                lines_truncated = True
            formatted.append(f"{line_number:>{padding}}\u2192{line}")

        result = "\n".join(formatted)

        # Add notices
        notices = []
        if end_line < total_lines and limit == DEFAULT_LINE_LIMIT:
            notices.append(
                f"\n\n[File truncated: showing lines {start_line + 1}-{end_line} of {total_lines} total. "
                "Use offset and limit parameters to read other sections.]"
            )
        if lines_truncated:
            notices.append(
                f"\n\n[Some lines exceeded {MAX_LINE_LENGTH} characters and were truncated.]"
            )

        return result + "".join(notices)

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        file_path = args.get("file_path")
        if not file_path:
            return ToolResult.error("file_path is required")

        offset = args.get("offset", 1)
        if offset is not None:
            offset = max(0, offset - 1)  # Convert from 1-indexed to 0-indexed
        else:
            offset = 0

        limit = args.get("limit", DEFAULT_LINE_LIMIT)

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.error(str(e))

        if not path.exists():
            return ToolResult.error(
                f"File does not exist. Attempted path: {path}. "
                f"Current working directory: {self.working_dir}"
            )

        if not path.is_file():
            return ToolResult.error(f"Path is a directory, not a file: {path}")

        # Check file size
        try:
            size = path.stat().st_size
            if size > MAX_FILE_SIZE:
                return ToolResult.error(f"File too large: {size} bytes (max {MAX_FILE_SIZE} bytes)")
        except OSError as e:
            return ToolResult.error(f"Cannot stat file: {e}")

        # Check for binary
        if self._is_binary_file(path):
            return ToolResult.error(f"Cannot read binary file: {path}")

        # Read file
        try:
            content = path.read_text(encoding="utf-8")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except OSError as e:
            return ToolResult.error(f"Failed to read file: {e}")

        # Handle empty file
        if not content.strip():
            return ToolResult.success(
                f"<system-reminder>\nThe file {path} exists but has empty contents.\n</system-reminder>"
            )

        formatted = self._format_with_line_numbers(content, offset, limit)
        return ToolResult.success(formatted)

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        path = args.get("file_path", "file")
        if result.is_error:
            return f"read {path} -> err: {result.output}"

        lines = result.output.split("\n")
        total = len(lines)
        if total <= 30:
            preview = result.output
        else:
            preview = "\n".join(lines[:30]) + f"\n... ({total - 30} more lines)"

        return f"read {path}\n{preview}"
