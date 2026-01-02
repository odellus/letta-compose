"""Agent management commands: /new, /agents, /pin, /unpin, /rename."""

from karla.commands.registry import register, CommandType
from karla.commands.context import CommandContext


@register("/new", "Create a new agent and switch to it", CommandType.API, order=20)
async def cmd_new(ctx: CommandContext) -> str:
    """Create a new agent and switch to it."""
    from karla.cli import create_agent, find_config
    from karla.letta import register_tools_with_letta
    from karla.tools import create_default_registry

    config = find_config()
    new_id = create_agent(ctx.client, config)
    ctx.settings.save_last_agent(new_id)

    # Register tools for the new agent
    registry = create_default_registry(ctx.working_dir)
    register_tools_with_letta(ctx.client, new_id, registry)

    # Update context to use new agent
    ctx.agent_id = new_id

    agent = ctx.client.agents.retrieve(new_id)
    return f"Created new agent: {agent.name} ({new_id})\nUse /pin to save it."


@register("/agents", "Browse all agents", CommandType.CLI, order=21)
async def cmd_agents(ctx: CommandContext) -> str:
    """List all agents."""
    agents = list(ctx.client.agents.list())

    if not agents:
        return "No agents found."

    lines = ["# Agents", ""]
    for agent in agents[:20]:  # Limit to 20
        marker = " *" if agent.id == ctx.agent_id else ""
        lines.append(f"  {agent.name or '(unnamed)'}{marker}")
        lines.append(f"    {agent.id}")

    if len(agents) > 20:
        lines.append(f"\n  ... and {len(agents) - 20} more")

    lines.append("\n* = current agent")
    return "\n".join(lines)


@register("/pin", "Pin current agent (use -l for local only)", CommandType.CLI, order=22)
async def cmd_pin(ctx: CommandContext, args: str = "") -> str:
    """Pin the current agent to settings."""
    local_only = "-l" in args or "--local" in args

    if local_only:
        ctx.settings.pin_agent(ctx.agent_id, local=True)
        return f"Pinned agent locally: {ctx.agent_id}"
    else:
        ctx.settings.pin_agent(ctx.agent_id, local=False)
        return f"Pinned agent globally: {ctx.agent_id}"


@register("/unpin", "Unpin current agent (use -l for local only)", CommandType.CLI, order=23)
async def cmd_unpin(ctx: CommandContext, args: str = "") -> str:
    """Unpin the current agent from settings."""
    local_only = "-l" in args or "--local" in args

    if local_only:
        ctx.settings.unpin_agent(ctx.agent_id, local=True)
        return f"Unpinned agent locally: {ctx.agent_id}"
    else:
        ctx.settings.unpin_agent(ctx.agent_id, local=False)
        return f"Unpinned agent globally: {ctx.agent_id}"


@register("/pinned", "Browse pinned agents", CommandType.CLI, order=24)
async def cmd_pinned(ctx: CommandContext) -> str:
    """List pinned agents."""
    pinned = ctx.settings.get_pinned_agents()

    if not pinned:
        return "No pinned agents. Use /pin to pin the current agent."

    lines = ["# Pinned Agents", ""]
    for agent_id in pinned:
        try:
            agent = ctx.client.agents.retrieve(agent_id)
            marker = " *" if agent_id == ctx.agent_id else ""
            lines.append(f"  {agent.name or '(unnamed)'}{marker}")
            lines.append(f"    {agent_id}")
        except Exception:
            lines.append(f"  (deleted)")
            lines.append(f"    {agent_id}")

    lines.append("\n* = current agent")
    return "\n".join(lines)


@register("/rename", "Rename the current agent (/rename <name>)", CommandType.API, order=25)
async def cmd_rename(ctx: CommandContext, args: str = "") -> str:
    """Rename the current agent."""
    new_name = args.strip()
    if not new_name:
        return "Usage: /rename <new_name>"

    ctx.client.agents.update(agent_id=ctx.agent_id, name=new_name)
    return f"Renamed agent to: {new_name}"
