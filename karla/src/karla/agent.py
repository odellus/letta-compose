"""Agent creation and management for Karla.

This module provides the main interface for creating and managing Karla agents
with proper memory blocks, tools, and configuration.
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from crow_client import Crow

from karla.config import KarlaConfig
from karla.executor import ToolExecutor
from karla.crow import register_tools_with_crow
from karla.memory import create_default_memory_blocks, get_block_ids
from karla.prompts import get_default_system_prompt
from karla.tools import create_default_registry

logger = logging.getLogger(__name__)


@dataclass
class KarlaAgent:
    """A Karla coding agent instance.

    This wraps a Crow agent with all the Karla-specific configuration:
    - System prompt from prompts/karla_main.md
    - Memory blocks (persona, skills, loaded_skills)
    - Client-side tools
    - Tool executor
    """

    client: Crow
    agent_id: str
    name: str
    executor: ToolExecutor
    working_dir: str

    @property
    def id(self) -> str:
        """Alias for agent_id."""
        return self.agent_id


def create_karla_agent(
    client: Crow,
    config: KarlaConfig,
    working_dir: str | Path,
    name: Optional[str] = None,
    with_memory_blocks: bool = True,
) -> KarlaAgent:
    """Create a new Karla agent with full configuration.

    This creates an agent with:
    1. Karla system prompt
    2. Memory blocks (persona, skills)
    3. All client-side tools registered
    4. Tool executor ready for use

    Args:
        client: Crow client
        config: Karla configuration
        working_dir: Working directory for tool execution
        name: Optional agent name (auto-generated if not provided)
        with_memory_blocks: Whether to create memory blocks (default True)

    Returns:
        KarlaAgent instance
    """
    working_dir = str(Path(working_dir).resolve())

    if name is None:
        name = f"karla-{uuid.uuid4().hex[:8]}"

    # Get system prompt with working directory injected
    system_prompt = get_default_system_prompt(working_dir=working_dir)

    # Create memory blocks if requested
    block_ids = []
    if with_memory_blocks:
        try:
            blocks = create_default_memory_blocks(client)
            block_ids = get_block_ids(blocks)
            logger.info("Created %d memory blocks", len(blocks))
        except Exception as e:
            logger.warning("Failed to create memory blocks: %s", e)

    # Create the Crow agent
    agent = client.agents.create(
        name=name,
        system=system_prompt,
        llm_config=config.llm.to_dict(),
        embedding=config.embedding.to_string(),
        include_base_tools=config.agent_defaults.include_base_tools,
        block_ids=block_ids if block_ids else None,
        kv_cache_friendly=config.agent_defaults.kv_cache_friendly,
    )

    logger.info("Created agent: %s (id=%s)", name, agent.id)

    # Create tool registry and executor
    registry = create_default_registry(working_dir)
    executor = ToolExecutor(registry, working_dir)

    # Register tools with the agent
    registered = register_tools_with_crow(client, agent.id, registry)
    logger.info("Registered %d tools with agent", len(registered))

    return KarlaAgent(
        client=client,
        agent_id=agent.id,
        name=name,
        executor=executor,
        working_dir=working_dir,
    )


def get_or_create_agent(
    client: Crow,
    config: KarlaConfig,
    working_dir: str | Path,
    agent_id: Optional[str] = None,
    create_if_missing: bool = True,
) -> Optional[KarlaAgent]:
    """Get an existing agent or create a new one.

    Args:
        client: Crow client
        config: Karla configuration
        working_dir: Working directory for tool execution
        agent_id: Optional agent ID to retrieve
        create_if_missing: If True, create new agent if ID doesn't exist

    Returns:
        KarlaAgent or None if agent not found and create_if_missing is False
    """
    working_dir = str(Path(working_dir).resolve())

    if agent_id:
        try:
            agent = client.agents.retrieve(agent_id)

            # Create registry and executor for existing agent
            registry = create_default_registry(working_dir)
            executor = ToolExecutor(registry, working_dir)

            # Re-register tools (they may have changed)
            register_tools_with_crow(client, agent.id, registry)

            return KarlaAgent(
                client=client,
                agent_id=agent.id,
                name=agent.name,
                executor=executor,
                working_dir=working_dir,
            )
        except Exception as e:
            logger.warning("Agent %s not found: %s", agent_id, e)
            if not create_if_missing:
                return None

    # Create new agent
    return create_karla_agent(client, config, working_dir)


def delete_agent(client: Crow, agent_id: str) -> bool:
    """Delete a Karla agent.

    Args:
        client: Crow client
        agent_id: Agent ID to delete

    Returns:
        True if deleted, False if not found
    """
    try:
        client.agents.delete(agent_id)
        logger.info("Deleted agent: %s", agent_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete agent %s: %s", agent_id, e)
        return False
