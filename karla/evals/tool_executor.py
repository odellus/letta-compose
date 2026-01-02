"""Tool executor for karla evals.

This module provides the tool execution function used by crow-evals
to execute karla tools client-side during evaluation.
"""

from typing import Any

from karla.executor import ToolExecutor
from karla.tools import create_default_registry

# Default working directory for evals - matches what's used in create_agent.py
EVAL_WORKING_DIR = "/tmp/karla-eval"

# Global executor instance
_executor: ToolExecutor | None = None


def _get_executor() -> ToolExecutor:
    """Get or create the executor."""
    global _executor
    if _executor is None:
        registry = create_default_registry(EVAL_WORKING_DIR)
        _executor = ToolExecutor(registry, EVAL_WORKING_DIR)
    return _executor


async def execute_tool(tool_name: str, tool_args: dict[str, Any]) -> tuple[str, bool]:
    """Execute a karla tool and return the result.

    This is the entry point called by crow-evals during evaluation.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool

    Returns:
        Tuple of (output_string, is_error)
    """
    executor = _get_executor()
    result = await executor.execute(tool_name, tool_args)
    return result.output, result.is_error
