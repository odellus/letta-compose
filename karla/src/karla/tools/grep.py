"""Grep tool - searches file contents using ripgrep."""

import asyncio
import shutil
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

MAX_RESULTS = 500


class GrepTool(Tool):
    """Search file contents using ripgrep."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = Path(working_dir).resolve()
        self._rg_path = shutil.which("rg")

    @property
    def name(self) -> str:
        return "Grep"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Grep",
            description="""Searches file contents using ripgrep.

Usage:
- Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Filter files with glob parameter (e.g., "*.js", "**/*.tsx")
- Output modes: "content" shows matching lines, "files_with_matches" shows only file paths
- Use for finding code patterns, function definitions, imports, etc.
- Respects .gitignore by default""",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (default: working directory)",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '*.py', '*.{ts,tsx}')",
                    },
                    "output_mode": {
                        "type": "string",
                        "description": "Output mode: 'content' or 'files_with_matches' (default)",
                        "enum": ["content", "files_with_matches"],
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case insensitive search (default false)",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context around matches (for content mode)",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = args.get("pattern")
        if not pattern:
            return ToolResult.error("pattern is required")

        if not self._rg_path:
            return ToolResult.error("ripgrep (rg) not found. Please install it.")

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        # Build ripgrep command
        cmd = [self._rg_path]

        # Output mode
        output_mode = args.get("output_mode", "files_with_matches")
        if output_mode == "files_with_matches":
            cmd.append("--files-with-matches")
        else:
            cmd.append("--line-number")
            context = args.get("context_lines")
            if context and context > 0:
                cmd.extend(["-C", str(min(context, 10))])

        # Case sensitivity
        if args.get("case_insensitive"):
            cmd.append("--ignore-case")

        # Glob filter
        glob = args.get("glob")
        if glob:
            cmd.extend(["--glob", glob])

        # Add pattern
        cmd.append(pattern)

        # Add path
        search_path = args.get("path", ".")
        if not Path(search_path).is_absolute():
            search_path = str(self.working_dir / search_path)
        cmd.append(search_path)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60,
            )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # ripgrep returns 1 for no matches, 2 for errors
            if process.returncode == 2:
                return ToolResult.error(f"Search error: {stderr_str}")

            if not stdout_str.strip():
                return ToolResult.success("No matches found")

            # Truncate results
            lines = stdout_str.strip().split("\n")
            if len(lines) > MAX_RESULTS:
                lines = lines[:MAX_RESULTS]
                lines.append(f"\n... [truncated, showing first {MAX_RESULTS} results]")

            output = "\n".join(lines)

            if output_mode == "files_with_matches":
                return ToolResult.success(f"Found {len(lines)} files:\n{output}")
            else:
                return ToolResult.success(output)

        except asyncio.TimeoutError:
            return ToolResult.error("Search timed out after 60 seconds")
        except Exception as e:
            return ToolResult.error(f"Search failed: {e}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        pattern = args.get("pattern", "pattern")
        if result.is_error:
            return f'grep "{pattern}" -> err'

        lines = result.output.split("\n")
        count = len([l for l in lines if l.strip() and not l.startswith("...")])
        return f'grep "{pattern}" -> {count} results'
