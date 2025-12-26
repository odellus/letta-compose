"""Background bash tools - BashOutput and KillBash for managing background processes."""

import asyncio
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

# Global registry of background processes
_background_processes: dict[str, asyncio.subprocess.Process] = {}
_process_outputs: dict[str, tuple[list[str], list[str]]] = {}  # stdout, stderr buffers
_process_counter = 0


def _get_next_id() -> str:
    global _process_counter
    _process_counter += 1
    return f"bg_{_process_counter}"


async def start_background_process(
    command: str,
    working_dir: str,
) -> tuple[str, str]:
    """Start a background process and return (id, initial_message)."""
    import os

    process_id = _get_next_id()

    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env={**os.environ, "TERM": "dumb"},
    )

    _background_processes[process_id] = process
    _process_outputs[process_id] = ([], [])

    # Start background readers
    asyncio.create_task(_read_output(process_id, process.stdout, is_stderr=False))
    asyncio.create_task(_read_output(process_id, process.stderr, is_stderr=True))

    return process_id, f"Started background process {process_id}"


async def _read_output(process_id: str, stream, is_stderr: bool):
    """Background task to read process output."""
    if stream is None:
        return

    try:
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if process_id in _process_outputs:
                idx = 1 if is_stderr else 0
                _process_outputs[process_id][idx].append(text)
    except Exception:
        pass


class BashOutputTool(Tool):
    """Get output from a background bash process."""

    @property
    def name(self) -> str:
        return "BashOutput"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="BashOutput",
            description="""Retrieves output from a running or completed background bash process.

Use this to check on the status and output of commands started in the background.
Returns new output since last check, along with process status.""",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The background process ID (e.g., 'bg_1')",
                    },
                },
                "required": ["id"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        process_id = args.get("id")
        if not process_id:
            return ToolResult.error("id is required")

        if process_id not in _background_processes:
            return ToolResult.error(f"No background process with id: {process_id}")

        process = _background_processes[process_id]
        stdout_lines, stderr_lines = _process_outputs.get(process_id, ([], []))

        # Drain the buffers
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        stdout_lines.clear()
        stderr_lines.clear()

        # Check if process is still running
        if process.returncode is None:
            status = "running"
        else:
            status = f"exited with code {process.returncode}"
            # Clean up finished process
            del _background_processes[process_id]
            del _process_outputs[process_id]

        output_parts = [f"Status: {status}"]
        if stdout.strip():
            output_parts.append(f"[stdout]\n{stdout.rstrip()}")
        if stderr.strip():
            output_parts.append(f"[stderr]\n{stderr.rstrip()}")
        if not stdout.strip() and not stderr.strip():
            output_parts.append("(no new output)")

        return ToolResult.success("\n".join(output_parts))

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        process_id = args.get("id", "?")
        return f"bash_output {process_id}"


class KillBashTool(Tool):
    """Kill a background bash process."""

    @property
    def name(self) -> str:
        return "KillBash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="KillBash",
            description="""Kills a running background bash process.

Use this to stop long-running or stuck background processes.""",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The background process ID to kill",
                    },
                },
                "required": ["id"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        process_id = args.get("id")
        if not process_id:
            return ToolResult.error("id is required")

        if process_id not in _background_processes:
            return ToolResult.error(f"No background process with id: {process_id}")

        process = _background_processes[process_id]

        if process.returncode is not None:
            # Already finished
            del _background_processes[process_id]
            if process_id in _process_outputs:
                del _process_outputs[process_id]
            return ToolResult.success(f"Process {process_id} already finished")

        try:
            process.kill()
            await process.wait()
        except Exception as e:
            return ToolResult.error(f"Failed to kill process: {e}")

        del _background_processes[process_id]
        if process_id in _process_outputs:
            del _process_outputs[process_id]

        return ToolResult.success(f"Killed process {process_id}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        process_id = args.get("id", "?")
        return f"kill_bash {process_id}"
