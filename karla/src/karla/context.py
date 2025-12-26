"""Agent context for shared state across tool executions."""

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from letta_client import Letta


@dataclass
class SubagentInfo:
    """Information about a running subagent."""

    id: str
    agent_id: str
    subagent_type: str
    description: str
    status: str  # "running", "completed", "error"
    result: str | None = None
    error: str | None = None


@dataclass
class AgentContext:
    """Shared context for agent execution.

    This holds references to the Letta client, current agent ID,
    and any running subagents.
    """

    client: "Letta"
    agent_id: str
    working_dir: str
    skills_dir: str | None = None

    # LLM configuration to use for subagents (inherited from parent)
    llm_config: dict | None = None
    embedding_config: str | None = None
    kv_cache_friendly: bool = True  # Default to kv_cache_friendly for local LLMs

    # Track running subagents
    _subagents: dict[str, SubagentInfo] = field(default_factory=dict)
    _subagent_futures: dict[str, asyncio.Future] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register_subagent(
        self,
        agent_id: str,
        subagent_type: str,
        description: str,
    ) -> str:
        """Register a new subagent and return its tracking ID."""
        tracking_id = f"subagent-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._subagents[tracking_id] = SubagentInfo(
                id=tracking_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                description=description,
                status="running",
            )
        return tracking_id

    def complete_subagent(self, tracking_id: str, result: str) -> None:
        """Mark a subagent as completed with its result."""
        with self._lock:
            if tracking_id in self._subagents:
                self._subagents[tracking_id].status = "completed"
                self._subagents[tracking_id].result = result

    def fail_subagent(self, tracking_id: str, error: str) -> None:
        """Mark a subagent as failed with an error."""
        with self._lock:
            if tracking_id in self._subagents:
                self._subagents[tracking_id].status = "error"
                self._subagents[tracking_id].error = error

    def get_subagent(self, tracking_id: str) -> SubagentInfo | None:
        """Get info about a subagent by tracking ID."""
        with self._lock:
            return self._subagents.get(tracking_id)

    def list_subagents(self) -> list[SubagentInfo]:
        """List all tracked subagents."""
        with self._lock:
            return list(self._subagents.values())


# Global context - set by the runtime when agent starts
_current_context: AgentContext | None = None


def get_context() -> AgentContext:
    """Get the current agent context.

    Raises:
        RuntimeError: If no context has been set.
    """
    if _current_context is None:
        raise RuntimeError(
            "No agent context set. Ensure the agent runtime has initialized the context."
        )
    return _current_context


def set_context(ctx: AgentContext) -> None:
    """Set the current agent context."""
    global _current_context
    _current_context = ctx


def clear_context() -> None:
    """Clear the current agent context."""
    global _current_context
    _current_context = None
