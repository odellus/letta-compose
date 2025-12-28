"""Headless execution mode for Karla.

This module provides headless (non-interactive) execution of Karla agents,
matching the functionality described in Letta Code's headless.ts.

Key functions:
- resolve_pending_approvals: Clear any pending tool approvals before new input
- run_headless: Execute a single prompt and return the result
"""

import logging
from typing import Optional

from letta_client import Letta

from karla.agent_loop import run_agent_loop, AgentResponse, OutputFormat, format_response
from karla.config import KarlaConfig, create_client
from karla.executor import ToolExecutor
from karla.letta import register_tools_with_letta
from karla.settings import SettingsManager
from karla.tools import create_default_registry

logger = logging.getLogger(__name__)


def resolve_pending_approvals(client: Letta, agent_id: str) -> None:
    """Clear any pending tool approvals before new input.

    This ensures the agent starts fresh without any dangling approval requests
    from previous sessions.

    Args:
        client: Letta client
        agent_id: Agent ID to clear approvals for
    """
    # Letta handles this automatically, but this function exists for
    # API compatibility with Letta Code's headless.ts
    pass


async def run_headless(
    prompt: str,
    config: KarlaConfig,
    working_dir: str,
    agent_id: Optional[str] = None,
    continue_last: bool = False,
    force_new: bool = False,
    output_format: OutputFormat = OutputFormat.TEXT,
    model_override: Optional[str] = None,
) -> tuple[AgentResponse, str]:
    """Run Karla in headless mode.

    This is the main entry point for non-interactive execution.
    It handles:
    1. Agent resolution (new, continue, or specific ID)
    2. Tool registration
    3. Running the agent loop
    4. Output formatting

    Args:
        prompt: User prompt to send
        config: Karla configuration
        working_dir: Working directory for tools
        agent_id: Explicit agent ID to use
        continue_last: Continue last agent session
        force_new: Force creation of new agent
        output_format: Output format (text, json, stream-json)
        model_override: Override the model from config

    Returns:
        Tuple of (AgentResponse, agent_id)
    """
    from karla.agent import create_karla_agent, get_or_create_agent as get_agent

    # Apply model override if provided
    if model_override:
        config.llm.model = model_override

    client = create_client(config)
    settings = SettingsManager(project_dir=working_dir)

    # Resolve agent
    if agent_id:
        # Use specific agent
        karla_agent = get_agent(client, config, working_dir, agent_id=agent_id)
        if karla_agent is None:
            raise ValueError(f"Agent {agent_id} not found")
    elif continue_last:
        # Try to continue last agent
        last_id = settings.get_last_agent()
        if last_id:
            karla_agent = get_agent(client, config, working_dir, agent_id=last_id)
            if karla_agent is None:
                logger.warning("Last agent %s not found, creating new", last_id)
                karla_agent = create_karla_agent(client, config, working_dir)
        else:
            karla_agent = create_karla_agent(client, config, working_dir)
    elif force_new:
        karla_agent = create_karla_agent(client, config, working_dir)
    else:
        # Default: create new agent
        karla_agent = create_karla_agent(client, config, working_dir)

    # Save as last agent
    settings.save_last_agent(karla_agent.agent_id)

    # Clear any pending approvals
    resolve_pending_approvals(client, karla_agent.agent_id)

    # Run the agent loop
    response = await run_agent_loop(
        client=client,
        agent_id=karla_agent.agent_id,
        executor=karla_agent.executor,
        message=prompt,
    )

    return response, karla_agent.agent_id


def format_headless_output(response: AgentResponse, format: OutputFormat) -> str:
    """Format the headless output.

    Args:
        response: AgentResponse from run_agent_loop
        format: Output format

    Returns:
        Formatted string for output
    """
    return format_response(response, format)
