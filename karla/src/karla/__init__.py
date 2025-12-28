"""Karla - A Python coding agent with Letta backend and ACP support."""

from karla.config import EmbeddingConfig, KarlaConfig, LLMConfig, create_client, load_config
from karla.context import AgentContext, clear_context, get_context, set_context
from karla.executor import ToolExecutor
from karla.registry import ToolRegistry
from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult
from karla.tools import create_default_registry

# Agent and loop
from karla.agent import KarlaAgent, create_karla_agent, get_or_create_agent
from karla.agent_loop import run_agent_loop, AgentResponse, OutputFormat

# Memory and skills
from karla.memory import MemoryBlock, create_default_memory_blocks
from karla.skills import Skill, discover_all_skills, format_skills_for_memory

# Settings
from karla.settings import SettingsManager

# Prompts
from karla.prompts import get_default_system_prompt, get_persona, load_system_prompt

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
    # Agent
    "KarlaAgent",
    "create_karla_agent",
    "get_or_create_agent",
    "run_agent_loop",
    "AgentResponse",
    "OutputFormat",
    # Memory and skills
    "MemoryBlock",
    "create_default_memory_blocks",
    "Skill",
    "discover_all_skills",
    "format_skills_for_memory",
    # Settings
    "SettingsManager",
    # Prompts
    "get_default_system_prompt",
    "get_persona",
    "load_system_prompt",
    # Version
    "__version__",
]
