"""Command registry for slash commands."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class CommandType(Enum):
    """Type of command."""
    API = "api"      # Calls Crow API directly
    PROMPT = "prompt"  # Sends prompt to agent
    CLI = "cli"       # Local CLI action


@dataclass
class Command:
    """A registered slash command."""
    name: str
    description: str
    handler: Callable
    command_type: CommandType
    hidden: bool = False
    order: int = 100


# Global command registry
COMMANDS: dict[str, Command] = {}


def register(
    name: str,
    desc: str,
    cmd_type: CommandType,
    order: int = 100,
    hidden: bool = False,
):
    """Decorator to register a command.

    Usage:
        @register("/clear", "Clear conversation", CommandType.API)
        async def cmd_clear(ctx: CommandContext) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        COMMANDS[name] = Command(
            name=name,
            description=desc,
            handler=func,
            command_type=cmd_type,
            hidden=hidden,
            order=order,
        )
        return func
    return decorator
