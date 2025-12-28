"""Command context passed to command handlers."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from letta_client import Letta
    from karla.settings import SettingsManager


@dataclass
class CommandContext:
    """Context passed to command handlers."""
    client: "Letta"
    agent_id: str
    working_dir: str
    settings: "SettingsManager"

    # Set by prompt commands to inject a message to the agent
    inject_prompt: Optional[str] = field(default=None)
