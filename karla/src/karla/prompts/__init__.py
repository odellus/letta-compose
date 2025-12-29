"""System prompts for Karla coding agent."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_system_prompt(name: str = "karla_main") -> str:
    """Load a system prompt by name.

    Args:
        name: Name of the prompt file (without .md extension)

    Returns:
        The prompt content as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    prompt_file = PROMPTS_DIR / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"System prompt not found: {name}")
    return prompt_file.read_text()


def get_default_system_prompt(working_dir: str | None = None) -> str:
    """Get the default Karla system prompt.

    Args:
        working_dir: Optional working directory to inject into prompt
    """
    prompt = load_system_prompt("karla_main")

    if working_dir:
        env_info = f"""
# Environment
Working directory: {working_dir}
"""
        # Insert after the first heading
        lines = prompt.split('\n')
        # Find first line after opening (after "You are Karla...")
        insert_idx = 2  # After first two lines
        for i, line in enumerate(lines):
            if line.startswith('# ') and i > 0:
                insert_idx = i
                break
        lines.insert(insert_idx, env_info)
        prompt = '\n'.join(lines)

    return prompt


def get_persona() -> str:
    """Get the default persona content for memory block."""
    return load_system_prompt("persona")


def get_human() -> str:
    """Get the default human content for memory block."""
    return load_system_prompt("human")


def get_project() -> str:
    """Get the default project content for memory block."""
    return load_system_prompt("project")


def list_available_prompts() -> list[str]:
    """List all available prompt names."""
    return [f.stem for f in PROMPTS_DIR.glob("*.md")]


__all__ = [
    "load_system_prompt",
    "get_default_system_prompt",
    "get_persona",
    "get_human",
    "get_project",
    "list_available_prompts",
    "PROMPTS_DIR",
]
