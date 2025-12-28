"""Slash commands for Karla CLI."""

from karla.commands.registry import Command, CommandType, COMMANDS, register
from karla.commands.context import CommandContext
from karla.commands.dispatcher import dispatch_command

__all__ = [
    "Command",
    "CommandType",
    "COMMANDS",
    "register",
    "CommandContext",
    "dispatch_command",
]

# Import command modules to register them
from karla.commands import core
from karla.commands import prompts
from karla.commands import agents
from karla.commands import config
from karla.commands import hotl
