"""Command dispatcher for slash commands."""

import logging
from karla.commands.registry import COMMANDS, CommandType
from karla.commands.context import CommandContext

logger = logging.getLogger(__name__)


async def dispatch_command(
    input_text: str,
    ctx: CommandContext,
) -> tuple[str, bool]:
    """Dispatch a slash command.

    Args:
        input_text: The user input (e.g., "/clear" or "/remember some text")
        ctx: Command context with client, agent_id, etc.

    Returns:
        Tuple of (output_message, should_continue_to_agent)
        - output_message: Text to display to user
        - should_continue_to_agent: If True and ctx.inject_prompt is set,
          send that prompt to the agent
    """
    if not input_text.startswith("/"):
        return "", True  # Not a command, send to agent

    parts = input_text.split(maxsplit=1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd_name not in COMMANDS:
        return f"Unknown command: {cmd_name}. Use /help for available commands.", False

    cmd = COMMANDS[cmd_name]

    try:
        # Call handler - pass args to all commands that accept them
        import inspect
        sig = inspect.signature(cmd.handler)
        if len(sig.parameters) > 1:  # More than just ctx
            result = await cmd.handler(ctx, args)
        else:
            result = await cmd.handler(ctx)

        # If command injected a prompt, signal to continue to agent
        if ctx.inject_prompt:
            return result, True

        return result, False

    except Exception as e:
        logger.exception("Command %s failed", cmd_name)
        return f"Command failed: {e}", False
