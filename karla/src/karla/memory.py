"""Memory block utilities for Karla agents.

Letta agents use memory blocks to maintain persistent state across conversations.
Karla uses the following blocks:
- persona: Agent identity and learned preferences
- human: Information about the user
- project: Project-specific knowledge and context
- skills: Available skills directory
- loaded_skills: Currently loaded skills
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from letta_client import Letta

from karla.prompts import get_human, get_persona, get_project

logger = logging.getLogger(__name__)


@dataclass
class MemoryBlock:
    """A memory block for the agent."""
    id: str
    label: str
    value: str
    description: Optional[str] = None


def create_persona_block(client: Letta) -> MemoryBlock:
    """Create the persona memory block.

    The persona block contains the agent's identity and learned preferences.
    It's initialized with default content from prompts/persona.md.

    Args:
        client: Letta client

    Returns:
        MemoryBlock with the created block's info
    """
    persona_content = get_persona()

    block = client.blocks.create(
        label="persona",
        value=persona_content,
    )

    logger.info("Created persona block: %s", block.id)

    return MemoryBlock(
        id=block.id,
        label="persona",
        value=persona_content,
        description="Agent identity and learned preferences",
    )


def create_human_block(client: Letta) -> MemoryBlock:
    """Create the human memory block.

    The human block contains information about the user.

    Args:
        client: Letta client

    Returns:
        MemoryBlock with the created block's info
    """
    human_content = get_human()

    block = client.blocks.create(
        label="human",
        value=human_content,
    )

    logger.info("Created human block: %s", block.id)

    return MemoryBlock(
        id=block.id,
        label="human",
        value=human_content,
        description="Information about the user",
    )


def create_project_block(client: Letta) -> MemoryBlock:
    """Create the project memory block.

    The project block contains project-specific knowledge and context.

    Args:
        client: Letta client

    Returns:
        MemoryBlock with the created block's info
    """
    project_content = get_project()

    block = client.blocks.create(
        label="project",
        value=project_content,
    )

    logger.info("Created project block: %s", block.id)

    return MemoryBlock(
        id=block.id,
        label="project",
        value=project_content,
        description="Project-specific knowledge and context",
    )


def create_skills_block(client: Letta, skills_list: str = "") -> MemoryBlock:
    """Create the skills directory memory block.

    Lists all available skills that can be loaded.

    Args:
        client: Letta client
        skills_list: Formatted list of available skills

    Returns:
        MemoryBlock with the created block's info
    """
    default_content = skills_list or "# Available Skills\n\nNo skills configured."

    block = client.blocks.create(
        label="skills",
        value=default_content,
    )

    logger.info("Created skills block: %s", block.id)

    return MemoryBlock(
        id=block.id,
        label="skills",
        value=default_content,
        description="Directory of available skills",
    )


def create_loaded_skills_block(client: Letta) -> MemoryBlock:
    """Create the loaded skills memory block.

    Tracks which skills are currently loaded into agent memory.

    Args:
        client: Letta client

    Returns:
        MemoryBlock with the created block's info
    """
    default_content = "# Loaded Skills\n\nNo skills currently loaded."

    block = client.blocks.create(
        label="loaded_skills",
        value=default_content,
    )

    logger.info("Created loaded_skills block: %s", block.id)

    return MemoryBlock(
        id=block.id,
        label="loaded_skills",
        value=default_content,
        description="Currently loaded skills",
    )


def create_default_memory_blocks(client: Letta, skills_list: str = "") -> list[MemoryBlock]:
    """Create all default memory blocks for a Karla agent.

    Args:
        client: Letta client
        skills_list: Optional formatted list of available skills

    Returns:
        List of created MemoryBlocks
    """
    blocks = [
        create_persona_block(client),
        create_human_block(client),
        create_project_block(client),
        create_skills_block(client, skills_list),
        create_loaded_skills_block(client),
    ]

    return blocks


def get_block_ids(blocks: list[MemoryBlock]) -> list[str]:
    """Get just the IDs from a list of memory blocks.

    Args:
        blocks: List of MemoryBlock instances

    Returns:
        List of block IDs
    """
    return [b.id for b in blocks]


def generate_project_context(working_dir: str) -> str:
    """Generate project context from the working directory.

    Collects information about:
    - Working directory path
    - Git branch and status (if git repo)
    - Key project files

    Args:
        working_dir: Path to the working directory

    Returns:
        Formatted project context string
    """
    cwd = Path(working_dir)
    lines = ["# Project Context", ""]
    lines.append(f"Working directory: {working_dir}")

    # Check if git repo
    git_dir = cwd / ".git"
    if git_dir.exists():
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                lines.append(f"Git branch: {branch}")

            # Get status summary
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                status_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
                modified = sum(1 for l in status_lines if l.startswith(" M") or l.startswith("M"))
                added = sum(1 for l in status_lines if l.startswith("A") or l.startswith("??"))
                deleted = sum(1 for l in status_lines if l.startswith(" D") or l.startswith("D"))

                status_parts = []
                if modified:
                    status_parts.append(f"{modified} modified")
                if added:
                    status_parts.append(f"{added} untracked/added")
                if deleted:
                    status_parts.append(f"{deleted} deleted")

                if status_parts:
                    lines.append(f"Git status: {', '.join(status_parts)}")
                else:
                    lines.append("Git status: clean")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Git not available or timed out

    # Key project files
    key_files = [
        "README.md", "README", "readme.md",
        "pyproject.toml", "setup.py", "setup.cfg",
        "package.json", "package-lock.json",
        "Cargo.toml", "go.mod", "Makefile",
        "Dockerfile", "docker-compose.yml",
        ".env.example", "requirements.txt",
    ]

    found_files = []
    for f in key_files:
        if (cwd / f).exists():
            found_files.append(f)

    if found_files:
        lines.append("")
        lines.append("## Key Files")
        for f in found_files[:10]:  # Limit to 10
            lines.append(f"- {f}")

    return "\n".join(lines)


def update_project_block(client: Letta, agent_id: str, working_dir: str) -> None:
    """Update the project memory block with current context.

    Args:
        client: Letta client
        agent_id: Agent ID to update
        working_dir: Working directory path
    """
    # Get project context
    context = generate_project_context(working_dir)

    # Find and update the project block
    for block in client.agents.blocks.list(agent_id):
        if block.label == "project":
            client.blocks.update(block.id, value=context)
            logger.info("Updated project block for agent %s", agent_id)
            return

    logger.warning("No project block found for agent %s", agent_id)
