"""Tool executor for running tools."""

import json
import logging
from typing import Any

from karla.registry import ToolRegistry
from karla.tool import ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tools from a registry."""

    def __init__(self, registry: ToolRegistry, working_dir: str) -> None:
        self.registry = registry
        self.working_dir = working_dir
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel any running tool execution."""
        self._cancelled = True

    def reset(self) -> None:
        """Reset cancellation state."""
        self._cancelled = False

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | str,
    ) -> ToolResult:
        """Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments as dict or JSON string

        Returns:
            ToolResult with output or error
        """
        # Parse args if string
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args) if tool_args.strip() else {}
            except json.JSONDecodeError as e:
                return ToolResult.error(f"Invalid JSON arguments: {e}")

        # Look up tool
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult.error(f"Unknown tool: {tool_name}")

        # Create context
        ctx = ToolContext(
            working_dir=self.working_dir,
            cancelled=self._cancelled,
        )

        # Execute
        try:
            result = await tool.execute(tool_args, ctx)

            # Log humanized version if available
            humanized = tool.humanize(tool_args, result)
            if humanized:
                logger.debug("Tool execution: %s", humanized)

            return result
        except Exception as e:
            logger.exception("Tool execution failed: %s", tool_name)
            return ToolResult.error(f"Tool execution failed: {e}")
