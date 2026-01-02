"""Configuration loading for karla agents."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from dotenv import load_dotenv


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} patterns in strings using environment variables."""
    if isinstance(obj, str):
        # Match ${VAR} or $VAR patterns
        pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

        def replace(match: re.Match) -> str:
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))

        return pattern.sub(replace, obj)
    elif isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


if TYPE_CHECKING:
    from crow_client import Crow


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    type: str  # "api" or "local"
    api_key: str | None = None
    base_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderConfig":
        return cls(
            type=data.get("type", "api"),
            api_key=data.get("api_key") or data.get("key"),  # support both formats
            base_url=data.get("base_url"),
        )


@dataclass
class LLMConfig:
    """LLM configuration for Crow agents."""

    model: str
    model_endpoint: str
    model_endpoint_type: str = "openai"
    context_window: int = 8000
    api_key: str | None = None  # API key for the endpoint

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for Crow client."""
        result = {
            "model": self.model,
            "model_endpoint": self.model_endpoint,
            "model_endpoint_type": self.model_endpoint_type,
            "context_window": self.context_window,
        }
        if self.api_key:
            result["api_key"] = self.api_key
        return result


@dataclass
class EmbeddingConfig:
    """Embedding configuration."""

    model: str  # e.g. "ollama/mxbai-embed-large:latest"

    def to_string(self) -> str:
        """Convert to string for Crow client."""
        return self.model


@dataclass
class ServerConfig:
    """Crow server configuration."""

    base_url: str = "http://localhost:8283"
    # Timeout for LLM requests in seconds. None = no timeout (wait forever)
    # Local LLMs can be very slow, so we default to no timeout
    timeout: float | None = None


@dataclass
class AgentDefaults:
    """Default settings for agent creation."""

    kv_cache_friendly: bool = True
    include_base_tools: bool = True


@dataclass
class HooksConfig:
    """Configuration for hooks.

    Each hook is a list of shell commands that execute on events.
    Commands receive event data as JSON on stdin and can:
    - Return JSON with "inject_message" to add context
    - Return JSON with "block": true to block the action
    - Return non-zero exit code to block the action
    """

    on_prompt_submit: list[str] = field(default_factory=list)
    on_tool_start: list[str] = field(default_factory=list)
    on_tool_end: list[str] = field(default_factory=list)
    on_message: list[str] = field(default_factory=list)
    on_loop_start: list[str] = field(default_factory=list)
    on_loop_end: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HooksConfig":
        """Create hooks config from a dictionary."""
        return cls(
            on_prompt_submit=data.get("on_prompt_submit", []),
            on_tool_start=data.get("on_tool_start", []),
            on_tool_end=data.get("on_tool_end", []),
            on_message=data.get("on_message", []),
            on_loop_start=data.get("on_loop_start", []),
            on_loop_end=data.get("on_loop_end", []),
        )


@dataclass
class KarlaConfig:
    """Top-level karla configuration."""

    llm: LLMConfig
    embedding: EmbeddingConfig
    server: ServerConfig = field(default_factory=ServerConfig)
    agent_defaults: AgentDefaults = field(default_factory=AgentDefaults)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    hooks: HooksConfig = field(default_factory=HooksConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KarlaConfig":
        """Create config from a dictionary."""
        # Parse providers first
        providers_data = data.get("providers", {})
        providers = {
            name: ProviderConfig.from_dict(pdata) for name, pdata in providers_data.items()
        }

        # Parse LLM config, resolving provider reference if present
        llm_data = data.get("llm", {})
        provider_name = llm_data.get("provider")

        # If a provider is specified, use its base_url and api_key
        model_endpoint = llm_data.get("model_endpoint", "")
        api_key = llm_data.get("api_key")

        if provider_name and provider_name in providers:
            provider = providers[provider_name]
            if provider.base_url and not model_endpoint:
                model_endpoint = provider.base_url
            if provider.api_key and not api_key:
                api_key = provider.api_key

        llm = LLMConfig(
            model=llm_data.get("model", ""),
            model_endpoint=model_endpoint,
            model_endpoint_type=llm_data.get("model_endpoint_type", "openai"),
            context_window=llm_data.get("context_window", 8000),
            api_key=api_key,
        )

        embedding_data = data.get("embedding", {})
        embedding = EmbeddingConfig(
            model=embedding_data.get("model", ""),
        )

        server_data = data.get("server", {})
        server = ServerConfig(
            base_url=server_data.get("base_url", "http://localhost:8283"),
            timeout=server_data.get("timeout"),  # None means no timeout
        )

        defaults_data = data.get("agent_defaults", {})
        agent_defaults = AgentDefaults(
            kv_cache_friendly=defaults_data.get("kv_cache_friendly", True),
            include_base_tools=defaults_data.get("include_base_tools", True),
        )

        # Parse hooks
        hooks_data = data.get("hooks", {})
        hooks = HooksConfig.from_dict(hooks_data)

        return cls(
            llm=llm,
            embedding=embedding,
            server=server,
            agent_defaults=agent_defaults,
            providers=providers,
            hooks=hooks,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "KarlaConfig":
        """Load config from a YAML file.

        Also loads .env file from the same directory and expands
        ${VAR} patterns in config values.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        # Load .env from config directory
        load_dotenv(path.parent / ".env")

        with open(path) as f:
            data = yaml.safe_load(f)

        # Expand environment variables
        data = _expand_env_vars(data or {})

        return cls.from_dict(data)

    @classmethod
    def find_and_load(cls, start_dir: str | Path | None = None) -> "KarlaConfig | None":
        """Find and load config from standard locations.

        Searches for karla.yaml in:
        1. Current directory
        2. .karla/config.yaml in current directory
        3. ~/.config/karla/config.yaml

        Args:
            start_dir: Directory to start searching from (default: cwd)

        Returns:
            KarlaConfig if found, None otherwise
        """
        if start_dir is None:
            start_dir = Path.cwd()
        start_dir = Path(start_dir)

        search_paths = [
            start_dir / "karla.yaml",
            start_dir / ".karla" / "config.yaml",
            Path.home() / ".config" / "karla" / "config.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return cls.from_yaml(path)

        return None


def load_config(path: str | Path | None = None) -> KarlaConfig:
    """Load karla configuration.

    Args:
        path: Explicit path to config file, or None to search standard locations

    Returns:
        KarlaConfig

    Raises:
        FileNotFoundError: If no config file is found
    """
    if path is not None:
        return KarlaConfig.from_yaml(path)

    config = KarlaConfig.find_and_load()
    if config is None:
        raise FileNotFoundError(
            "No karla config found. Create karla.yaml or ~/.config/karla/config.yaml"
        )

    return config


def create_client(config: KarlaConfig) -> "Crow":
    """Create a Crow client from karla config.

    This creates a client with appropriate timeout settings for local LLMs.

    Args:
        config: KarlaConfig instance

    Returns:
        Configured Crow client
    """
    from crow_client import Crow

    return Crow(
        base_url=config.server.base_url,
        timeout=config.server.timeout,  # None = no timeout
    )
