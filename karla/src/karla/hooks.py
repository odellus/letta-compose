"""Hooks system for Karla - execute callbacks on agent events.

Hooks can be:
- Shell commands (strings) - executed with event data as JSON in stdin
- Python callables - called with event data as dict

Hook events:
- on_prompt_submit: User submits a prompt
- on_tool_start: Before a tool executes
- on_tool_end: After a tool executes
- on_message: Agent sends a message
- on_loop_start: Agent loop starts
- on_loop_end: Agent loop ends
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Hook callback types
SyncHookCallback = Callable[[dict[str, Any]], dict[str, Any] | None]
AsyncHookCallback = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
HookCallback = SyncHookCallback | AsyncHookCallback | str  # str = shell command


@dataclass
class HookResult:
    """Result from a hook execution."""
    success: bool
    output: str | None = None
    error: str | None = None
    # If set, this message will be injected into the conversation
    inject_message: str | None = None
    # If True, the action that triggered the hook should be blocked
    block: bool = False


@dataclass
class HooksConfig:
    """Configuration for hooks."""
    on_prompt_submit: list[HookCallback] = field(default_factory=list)
    on_tool_start: list[HookCallback] = field(default_factory=list)
    on_tool_end: list[HookCallback] = field(default_factory=list)
    on_message: list[HookCallback] = field(default_factory=list)
    on_loop_start: list[HookCallback] = field(default_factory=list)
    on_loop_end: list[HookCallback] = field(default_factory=list)


class HooksManager:
    """Manages hook execution."""

    def __init__(self, config: HooksConfig | None = None):
        self.config = config or HooksConfig()

    def add_hook(self, event: str, callback: HookCallback) -> None:
        """Add a hook for an event."""
        hooks = getattr(self.config, event, None)
        if hooks is None:
            raise ValueError(f"Unknown hook event: {event}")
        hooks.append(callback)

    def remove_hook(self, event: str, callback: HookCallback) -> None:
        """Remove a hook for an event."""
        hooks = getattr(self.config, event, None)
        if hooks and callback in hooks:
            hooks.remove(callback)

    async def run_hooks(
        self,
        event: str,
        data: dict[str, Any],
        timeout: float = 30.0,
    ) -> list[HookResult]:
        """Run all hooks for an event.

        Args:
            event: The event name (e.g., "on_tool_start")
            data: Event data to pass to hooks
            timeout: Timeout for shell command hooks

        Returns:
            List of HookResult from each hook
        """
        hooks = getattr(self.config, event, [])
        if not hooks:
            return []

        results = []
        for hook in hooks:
            try:
                result = await self._run_hook(hook, data, timeout)
                results.append(result)
            except Exception as e:
                logger.exception(f"Hook {hook} failed")
                results.append(HookResult(
                    success=False,
                    error=str(e),
                ))

        return results

    async def _run_hook(
        self,
        hook: HookCallback,
        data: dict[str, Any],
        timeout: float,
    ) -> HookResult:
        """Run a single hook."""
        if isinstance(hook, str):
            return await self._run_shell_hook(hook, data, timeout)
        elif asyncio.iscoroutinefunction(hook):
            result = await hook(data)
            return self._parse_callback_result(result)
        else:
            result = hook(data)
            return self._parse_callback_result(result)

    async def _run_shell_hook(
        self,
        command: str,
        data: dict[str, Any],
        timeout: float,
    ) -> HookResult:
        """Run a shell command hook."""
        try:
            # Pass event data as JSON on stdin
            input_json = json.dumps(data)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input_json.encode()),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return HookResult(
                    success=False,
                    error=f"Hook timed out after {timeout}s",
                )

            output = stdout.decode().strip()
            error_output = stderr.decode().strip()

            if proc.returncode != 0:
                return HookResult(
                    success=False,
                    output=output,
                    error=error_output or f"Exit code {proc.returncode}",
                    block=True,  # Non-zero exit = block the action
                )

            # Try to parse output as JSON for structured response
            try:
                response = json.loads(output) if output else {}
                return HookResult(
                    success=True,
                    output=output,
                    inject_message=response.get("inject_message"),
                    block=response.get("block", False),
                )
            except json.JSONDecodeError:
                # Plain text output
                return HookResult(
                    success=True,
                    output=output,
                )

        except Exception as e:
            return HookResult(
                success=False,
                error=str(e),
            )

    def _parse_callback_result(
        self,
        result: dict[str, Any] | None,
    ) -> HookResult:
        """Parse a callback result into HookResult."""
        if result is None:
            return HookResult(success=True)

        return HookResult(
            success=result.get("success", True),
            output=result.get("output"),
            error=result.get("error"),
            inject_message=result.get("inject_message"),
            block=result.get("block", False),
        )


# Global hooks manager instance
_hooks_manager: HooksManager | None = None


def get_hooks_manager() -> HooksManager:
    """Get the global hooks manager."""
    global _hooks_manager
    if _hooks_manager is None:
        _hooks_manager = HooksManager()
    return _hooks_manager


def set_hooks_manager(manager: HooksManager) -> None:
    """Set the global hooks manager."""
    global _hooks_manager
    _hooks_manager = manager


def add_hook(event: str, callback: HookCallback) -> None:
    """Add a hook to the global manager."""
    get_hooks_manager().add_hook(event, callback)


async def run_hooks(event: str, data: dict[str, Any]) -> list[HookResult]:
    """Run hooks on the global manager."""
    return await get_hooks_manager().run_hooks(event, data)
