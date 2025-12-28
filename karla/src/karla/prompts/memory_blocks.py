"""Memory block loading utilities for Karla agents.

This module provides utilities for loading memory block content from
the prompts directory, particularly the persona block.
"""

from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).parent


def load_persona() -> str:
    """Load the default persona content for the persona memory block.

    Returns:
        Content of persona.md
    """
    persona_file = PROMPTS_DIR / "persona.md"
    if not persona_file.exists():
        return "I am Karla, a Python-based AI coding assistant."
    return persona_file.read_text()


def load_memory_block(name: str) -> Optional[str]:
    """Load a memory block template by name.

    Args:
        name: Name of the memory block (e.g., "persona", "skills")

    Returns:
        Content of the block template, or None if not found
    """
    block_file = PROMPTS_DIR / f"{name}.md"
    if not block_file.exists():
        return None
    return block_file.read_text()


def get_default_memory_blocks() -> dict[str, str]:
    """Get all default memory block contents.

    Returns:
        Dictionary mapping block labels to their content
    """
    blocks = {}

    # Persona block
    persona = load_persona()
    if persona:
        blocks["persona"] = persona

    return blocks
