"""Settings persistence for Karla coding agent."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ProjectSettings:
    """Project-level settings stored in .karla/settings.local.json."""
    last_agent: Optional[str] = None


@dataclass
class GlobalSettings:
    """Global settings stored in ~/.karla/settings.json."""
    last_agent: Optional[str] = None
    default_model: Optional[str] = None


class SettingsManager:
    """Manages Karla settings persistence.

    Settings are stored in two locations:
    - Global: ~/.karla/settings.json
    - Project: .karla/settings.local.json

    Project settings take precedence over global settings.
    """

    def __init__(self, project_dir: Optional[Path | str] = None):
        self.global_dir = Path.home() / ".karla"
        self.global_path = self.global_dir / "settings.json"

        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.local_dir = self.project_dir / ".karla"
        self.local_path = self.local_dir / "settings.local.json"

    def load_global(self) -> GlobalSettings:
        """Load global settings."""
        if not self.global_path.exists():
            return GlobalSettings()

        try:
            data = json.loads(self.global_path.read_text())
            return GlobalSettings(**data)
        except (json.JSONDecodeError, TypeError):
            return GlobalSettings()

    def load_local(self) -> ProjectSettings:
        """Load project-level settings."""
        if not self.local_path.exists():
            return ProjectSettings()

        try:
            data = json.loads(self.local_path.read_text())
            return ProjectSettings(**data)
        except (json.JSONDecodeError, TypeError):
            return ProjectSettings()

    def save_global(self, settings: GlobalSettings) -> None:
        """Save global settings."""
        self.global_dir.mkdir(parents=True, exist_ok=True)
        self.global_path.write_text(json.dumps(asdict(settings), indent=2))

    def save_local(self, settings: ProjectSettings) -> None:
        """Save project-level settings."""
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(json.dumps(asdict(settings), indent=2))

    def get_last_agent(self) -> Optional[str]:
        """Get last agent ID (project first, then global)."""
        local = self.load_local()
        if local.last_agent:
            return local.last_agent

        global_ = self.load_global()
        if global_.last_agent:
            return global_.last_agent

        return None

    def save_last_agent(self, agent_id: str) -> None:
        """Save agent ID to both project and global settings."""
        local = self.load_local()
        local.last_agent = agent_id
        self.save_local(local)

        global_ = self.load_global()
        global_.last_agent = agent_id
        self.save_global(global_)

    def get_default_model(self) -> Optional[str]:
        """Get default model from global settings."""
        global_ = self.load_global()
        return global_.default_model

    def set_default_model(self, model: str) -> None:
        """Set default model in global settings."""
        global_ = self.load_global()
        global_.default_model = model
        self.save_global(global_)
