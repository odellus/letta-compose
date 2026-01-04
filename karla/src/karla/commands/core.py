"""Core slash commands: /clear, /compact, /memory, /help, /exit."""

from karla.commands.registry import register, CommandType, COMMANDS
from karla.commands.context import CommandContext
from karla.memory import update_project_block, update_system_prompt


@register("/clear", "Clear conversation history", CommandType.API, order=10)
async def cmd_clear(ctx: CommandContext) -> str:
    """Reset the agent's message buffer and refresh project context."""
    ctx.client.agents.messages.reset(
        agent_id=ctx.agent_id,
        add_default_initial_messages=False,
    )

    # Refresh BOTH the system prompt AND the project memory block
    # The system prompt has a hardcoded "Working directory:" that must be updated
    update_system_prompt(ctx.client, ctx.agent_id, ctx.working_dir)
    update_project_block(ctx.client, ctx.agent_id, ctx.working_dir)

    return "Conversation cleared. Project context refreshed."


@register("/compact", "Summarize conversation history", CommandType.API, order=11)
async def cmd_compact(ctx: CommandContext) -> str:
    """Compact/summarize the conversation."""
    import json
    import httpx

    # Count messages before compact
    messages_before = list(ctx.client.agents.messages.list(agent_id=ctx.agent_id, limit=1000))
    count_before = len(messages_before)

    try:
        result = ctx.client.agents.messages.compact(agent_id=ctx.agent_id)

        # Also refresh system prompt and project block to ensure consistency
        update_system_prompt(ctx.client, ctx.agent_id, ctx.working_dir)
        update_project_block(ctx.client, ctx.agent_id, ctx.working_dir)

        return f"Compacted {result.num_messages_before} -> {result.num_messages_after} messages. Context refreshed."
    except json.JSONDecodeError:
        # Letta server returns 204 No Content on success, but SDK expects JSON.
        # Work around by counting messages after the operation.
        messages_after = list(ctx.client.agents.messages.list(agent_id=ctx.agent_id, limit=1000))
        count_after = len(messages_after)

        # Refresh context
        update_system_prompt(ctx.client, ctx.agent_id, ctx.working_dir)
        update_project_block(ctx.client, ctx.agent_id, ctx.working_dir)

        if count_after < count_before:
            return f"Compacted {count_before} -> {count_after} messages. Context refreshed."
        else:
            return f"Conversation summarized ({count_after} messages). Context refreshed."
    except Exception as e:
        # Compact may not be available on all Crow server versions
        return f"Compact not available: {e}"


@register("/refresh", "Refresh project context (git status, files)", CommandType.CLI, order=13)
async def cmd_refresh(ctx: CommandContext) -> str:
    """Refresh the project memory block with current environment."""
    # Update both system prompt and project memory block
    update_system_prompt(ctx.client, ctx.agent_id, ctx.working_dir)
    update_project_block(ctx.client, ctx.agent_id, ctx.working_dir)
    return "Project context refreshed (cwd, git status, key files)."


@register("/memory", "View memory blocks", CommandType.CLI, order=12)
async def cmd_memory(ctx: CommandContext) -> str:
    """Display current memory blocks."""
    agent = ctx.client.agents.retrieve(agent_id=ctx.agent_id)

    lines = ["# Memory Blocks", ""]
    for block in agent.memory.blocks:
        lines.append(f"## {block.label}")
        value = block.value or "(empty)"
        # Truncate long blocks
        if len(value) > 500:
            value = value[:500] + "..."
        lines.append(value)
        lines.append("")

    return "\n".join(lines)


@register("/help", "Show available commands", CommandType.CLI, order=100)
async def cmd_help(ctx: CommandContext) -> str:
    """List all available commands."""
    lines = ["# Available Commands", ""]

    sorted_cmds = sorted(COMMANDS.items(), key=lambda x: x[1].order)
    for name, cmd in sorted_cmds:
        if not cmd.hidden:
            lines.append(f"  {name:15} {cmd.description}")

    return "\n".join(lines)


@register("/exit", "Exit interactive mode", CommandType.CLI, order=101)
async def cmd_exit(ctx: CommandContext) -> str:
    """Exit the interactive session."""
    return "Goodbye!"
