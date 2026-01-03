"""Glob tool - finds files by pattern."""

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

MAX_RESULTS = 500


class GlobTool(Tool):
    """Find files matching glob patterns."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "Glob"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Glob",
            description="""Finds files matching a glob pattern.

Usage:
- Supports patterns like "**/*.py", "src/**/*.ts", "*.json"
- Returns file paths sorted by modification time (newest first)
- Use this when you need to find files by name patterns
- For searching file contents, use Grep instead""",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g., '**/*.py')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: working directory)",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = args.get("pattern")
        if not pattern:
            return ToolResult.error("pattern is required")

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        # Determine search directory
        search_path = args.get("path", ".")
        if not Path(search_path).is_absolute():
            search_dir = self.working_dir / search_path
        else:
            search_dir = Path(search_path)

        try:
            search_dir = search_dir.resolve()
        except OSError as e:
            return ToolResult.error(f"Invalid path: {e}")

        # Security check
        try:
            search_dir.relative_to(self.working_dir)
        except ValueError:
            # Allow /tmp paths for testing
            if not str(search_dir).startswith("/tmp/"):
                return ToolResult.error(f"Path is outside working directory: {search_path}")

        if not search_dir.exists():
            return ToolResult.error(f"Directory does not exist: {search_dir}")

        # Find matching files
        try:
            matches = list(search_dir.glob(pattern))
        except Exception as e:
            return ToolResult.error(f"Invalid glob pattern: {e}")

        if not matches:
            return ToolResult.success("No files found matching pattern")

        # Filter to files only (not directories) and sort by mtime
        files = []
        for p in matches:
            if p.is_file():
                try:
                    mtime = p.stat().st_mtime
                    # Get relative path from working dir
                    rel_path = p.relative_to(self.working_dir)
                    files.append((mtime, str(rel_path)))
                except OSError:
                    continue

        # Sort by mtime descending (newest first)
        files.sort(key=lambda x: x[0], reverse=True)

        # Truncate if too many
        truncated = False
        if len(files) > MAX_RESULTS:
            files = files[:MAX_RESULTS]
            truncated = True

        # Format output
        output_lines = [f[1] for f in files]
        output = "\n".join(output_lines)

        if truncated:
            output += f"\n\n... [showing first {MAX_RESULTS} of {len(matches)} files]"

        return ToolResult.success(f"Found {len(files)} files:\n{output}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        pattern = args.get("pattern", "pattern")
        if result.is_error:
            return f"glob {pattern} -> err"

        lines = result.output.split("\n")
        count = len([l for l in lines if l.strip() and not l.startswith("...")])
        return f"glob {pattern} -> {count} files"
