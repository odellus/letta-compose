"""Core slash commands: /clear, /compact, /memory, /help, /exit."""

from karla.commands.registry import register, CommandType, COMMANDS
from karla.commands.context import CommandContext


@register("/clear", "Clear conversation history", CommandType.API, order=10)
async def cmd_clear(ctx: CommandContext) -> str:
    """Reset the agent's message buffer."""
    ctx.client.agents.messages.reset(
        agent_id=ctx.agent_id,
        add_default_initial_messages=False,
    )
    return "Conversation cleared. Memory blocks preserved."


@register("/compact", "Summarize conversation history", CommandType.API, order=11)
async def cmd_compact(ctx: CommandContext) -> str:
    """Compact/summarize the conversation."""
    try:
        result = ctx.client.agents.messages.compact(agent_id=ctx.agent_id)
        return f"Compacted {result.num_messages_before} -> {result.num_messages_after} messages"
    except Exception as e:
        # Compact may not be available on all Letta server versions
        return f"Compact not available: {e}"


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
