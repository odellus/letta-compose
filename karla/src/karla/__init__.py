"""Karla - A Python coding agent with Letta backend and ACP support."""

from karla.config import EmbeddingConfig, KarlaConfig, LLMConfig, create_client, load_config
from karla.context import AgentContext, clear_context, get_context, set_context
from karla.executor import ToolExecutor
from karla.registry import ToolRegistry
from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult
from karla.tools import create_default_registry

__version__ = "0.1.0"
__all__ = [
    # Core
    "ToolRegistry",
    "ToolExecutor",
    "Tool",
    "ToolResult",
    "ToolDefinition",
    "ToolContext",
    "create_default_registry",
    # Config
    "KarlaConfig",
    "LLMConfig",
    "EmbeddingConfig",
    "load_config",
    "create_client",
    # Agent context
    "AgentContext",
    "get_context",
    "set_context",
    "clear_context",
    # Version
    "__version__",
]
