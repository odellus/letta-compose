"""Write file tool - creates or overwrites files."""

import os
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult


class WriteTool(Tool):
    """Write content to a file."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "Write"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Write",
            description="""Writes content to a file, creating it if it doesn't exist or overwriting if it does.

Usage:
- The file_path parameter must be an absolute path
- Parent directories will be created if they don't exist
- This tool will overwrite existing files
- ALWAYS prefer editing existing files over creating new ones
- NEVER proactively create documentation files unless explicitly requested""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        )

    def _resolve_path(self, path: str) -> Path:
        """Resolve and validate a path."""
        requested = Path(path)
        if requested.is_absolute():
            full_path = requested
        else:
            full_path = self.working_dir / requested

        # Resolve parent to check working dir constraint
        # (file itself may not exist yet)
        try:
            parent = full_path.parent.resolve()
        except OSError as e:
            raise ValueError(f"Cannot resolve path: {e}")

        # Security: ensure path is within working directory or /tmp (for testing)
        try:
            parent.relative_to(self.working_dir)
        except ValueError:
            # Allow /tmp paths for testing
            if not str(parent).startswith("/tmp/"):
                raise ValueError(f"Path is outside working directory: {path}")

        return full_path

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        file_path = args.get("file_path")
        content = args.get("content")

        if not file_path:
            return ToolResult.error("file_path is required")
        if content is None:
            return ToolResult.error("content is required")

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.error(str(e))

        # Create parent directories if needed
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return ToolResult.error(f"Permission denied creating directory: {path.parent}")
        except OSError as e:
            return ToolResult.error(f"Failed to create directory: {e}")

        # Write file
        try:
            path.write_text(content, encoding="utf-8")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except OSError as e:
            return ToolResult.error(f"Failed to write file: {e}")

        lines = content.count("\n") + 1
        return ToolResult.success(f"Successfully wrote {lines} lines to {path}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        path = args.get("file_path", "file")
        if result.is_error:
            return f"write {path} -> err: {result.output}"
        return f"write {path} -> ok"
