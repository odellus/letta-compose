"""Bash tool - executes shell commands."""

import asyncio
import os
import shlex
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

DEFAULT_TIMEOUT = 120  # seconds
MAX_OUTPUT_SIZE = 100_000  # characters


class BashTool(Tool):
    """Execute bash commands."""

    def __init__(self, shell: str = "/bin/bash") -> None:
        self.shell = shell

    @property
    def name(self) -> str:
        return "Bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Bash",
            description="""Executes a bash command in the shell.

Usage:
- Use this for running system commands, build tools, tests, git operations, etc.
- Commands run in the current working directory
- Provide a clear description of what the command does
- For long-running commands, consider using timeout parameter
- Output is captured from both stdout and stderr

Note: Prefer specialized tools (Read, Write, Edit, Grep, Glob) over bash equivalents
when available - they provide better error handling and output formatting.""",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this command does (5-10 words)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120, max 120)",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = args.get("command")
        if not command:
            return ToolResult.error("command is required")

        timeout = min(args.get("timeout", DEFAULT_TIMEOUT), DEFAULT_TIMEOUT)

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ctx.working_dir,
                shell=True,
                env={**os.environ, "TERM": "dumb"},  # Disable color codes
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.error(f"Command timed out after {timeout} seconds")

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate if too large
            if len(stdout_str) > MAX_OUTPUT_SIZE:
                stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + "\n... [output truncated]"
            if len(stderr_str) > MAX_OUTPUT_SIZE:
                stderr_str = stderr_str[:MAX_OUTPUT_SIZE] + "\n... [stderr truncated]"

            # Build output
            output_parts = []
            if stdout_str.strip():
                output_parts.append(stdout_str.rstrip())
            if stderr_str.strip():
                output_parts.append(f"[stderr]\n{stderr_str.rstrip()}")
            if process.returncode != 0:
                output_parts.append(f"[exit code: {process.returncode}]")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            return ToolResult(
                output=output,
                is_error=process.returncode != 0,
                stdout=stdout_str if stdout_str.strip() else None,
                stderr=stderr_str if stderr_str.strip() else None,
            )

        except Exception as e:
            return ToolResult.error(f"Failed to execute command: {e}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        command = args.get("command", "command")
        # Truncate long commands
        if len(command) > 60:
            command = command[:57] + "..."

        if result.is_error:
            return f"$ {command} -> error"
        return f"$ {command} -> ok"
