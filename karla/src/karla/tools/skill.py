"""Skill tool - manages skill loading/unloading in Crow memory blocks."""

import logging
import re
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Default skills directory name
SKILLS_DIR = ".skills"


def parse_loaded_skills(value: str) -> dict[str, tuple[int, int]]:
    """Parse loaded_skills block content to extract skill IDs and their boundaries.

    Returns:
        Dict mapping skill ID to (start, end) positions in the content.
    """
    skill_map: dict[str, tuple[int, int]] = {}
    skill_header_regex = re.compile(r"# Skill: ([^\n]+)")

    headers: list[tuple[str, int]] = []

    # Find all skill headers
    for match in skill_header_regex.finditer(value):
        skill_id = match.group(1).strip()
        if skill_id:
            headers.append((skill_id, match.start()))

    # Determine boundaries for each skill
    for i, (skill_id, start) in enumerate(headers):
        if i + 1 < len(headers):
            next_start = headers[i + 1][1]
            # Find separator before next skill
            substring = value[start:next_start]
            sep_pos = substring.rfind("\n\n---\n\n")
            if sep_pos != -1:
                end = start + sep_pos
            else:
                end = next_start
        else:
            end = len(value)

        skill_map[skill_id] = (start, end)

    return skill_map


def get_loaded_skill_ids(value: str) -> list[str]:
    """Extract list of loaded skill IDs from block content."""
    skill_regex = re.compile(r"# Skill: ([^\n]+)")
    skills = []
    for match in skill_regex.finditer(value):
        skill_id = match.group(1).strip()
        if skill_id:
            skills.append(skill_id)
    return skills


def extract_skills_dir(skills_block_value: str) -> str | None:
    """Extract skills directory from skills block value."""
    match = re.search(r"Skills Directory: (.+)", skills_block_value)
    return match.group(1).strip() if match else None


class SkillTool(Tool):
    """Manage skill loading and unloading via Crow memory blocks.

    Skills are markdown files (SKILL.md) that contain context-specific
    instructions, patterns, or knowledge. This tool loads them into the
    agent's memory so they become part of the context.
    """

    def __init__(self, skills_dir: str | None = None) -> None:
        """Initialize with optional skills directory."""
        self._skills_dir = skills_dir

    @property
    def name(self) -> str:
        return "Skill"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Skill",
            description="""Manage skill loading and unloading in agent memory.

Skills are specialized context files (SKILL.md) that provide domain-specific
instructions, patterns, or knowledge. Load skills to gain expertise in a domain.

Commands:
- load: Load specified skills into memory
- unload: Remove skills from memory
- refresh: Rediscover available skills from the skills directory

Usage:
- Use 'refresh' first to see what skills are available
- Load skills relevant to the current task
- Unload skills when no longer needed to save context space""",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command: 'load', 'unload', or 'refresh'",
                        "enum": ["load", "unload", "refresh"],
                    },
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of skill IDs to load/unload (not needed for refresh)",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = args.get("command")
        skill_ids = args.get("skills", [])

        if command not in ("load", "unload", "refresh"):
            return ToolResult.error(
                f'Invalid command "{command}". Must be "load", "unload", or "refresh".'
            )

        # For load/unload, skills array is required
        if command != "refresh":
            if not skill_ids or not isinstance(skill_ids, list):
                return ToolResult.error(
                    f'Skill tool requires a non-empty "skills" array for "{command}" command'
                )

        # Get the agent context
        try:
            from karla.context import get_context

            agent_ctx = get_context()
        except RuntimeError:
            return ToolResult.error(
                "No agent context available. Skill tool requires Crow integration."
            )

        client = agent_ctx.client
        agent_id = agent_ctx.agent_id

        # Resolve skills directory
        skills_dir = await self._get_skills_dir(client, agent_id, ctx.working_dir)

        try:
            if command == "refresh":
                return await self._refresh_skills(client, agent_id, skills_dir)
            elif command == "load":
                return await self._load_skills(client, agent_id, skills_dir, skill_ids)
            else:  # unload
                return await self._unload_skills(client, agent_id, skill_ids)
        except Exception as e:
            logger.exception(f"Skill {command} failed")
            return ToolResult.error(f"Failed to {command} skill(s): {e}")

    async def _get_skills_dir(self, client: "Crow", agent_id: str, working_dir: str) -> Path:
        """Get the skills directory, trying multiple sources."""
        if self._skills_dir:
            return Path(self._skills_dir)

        # Try to extract from skills block
        try:
            skills_block = client.agents.blocks.retrieve(
                agent_id=agent_id,
                block_label="skills",
            )
            if skills_block and skills_block.value:
                extracted = extract_skills_dir(skills_block.value)
                if extracted:
                    return Path(extracted)
        except Exception:
            pass

        # Fall back to default .skills directory
        return Path(working_dir) / SKILLS_DIR

    async def _refresh_skills(self, client: "Crow", agent_id: str, skills_dir: Path) -> ToolResult:
        """Discover and list available skills."""
        skills = []
        errors = []

        # Discover skills from directory
        if skills_dir.exists() and skills_dir.is_dir():
            for skill_path in skills_dir.iterdir():
                if skill_path.is_dir():
                    skill_file = skill_path / "SKILL.md"
                    if skill_file.exists():
                        try:
                            content = skill_file.read_text()
                            # Extract first line as description
                            first_line = content.strip().split("\n")[0]
                            if first_line.startswith("#"):
                                first_line = first_line.lstrip("#").strip()
                            skills.append(
                                {
                                    "id": skill_path.name,
                                    "description": first_line[:100],
                                }
                            )
                        except Exception as e:
                            errors.append(f"{skill_path.name}: {e}")

        # Format skills for memory block
        lines = [f"Skills Directory: {skills_dir}"]
        lines.append("")
        if skills:
            lines.append("Available Skills:")
            for skill in skills:
                lines.append(f"  - {skill['id']}: {skill['description']}")
        else:
            lines.append("No skills found in skills directory.")

        formatted = "\n".join(lines)

        # Update the skills block
        try:
            client.agents.blocks.update(
                agent_id=agent_id,
                block_label="skills",
                value=formatted,
            )
        except Exception as e:
            # Block might not exist, try to create it
            logger.warning(f"Failed to update skills block: {e}")

        error_msg = f", {len(errors)} error(s)" if errors else ""
        return ToolResult.success(f"Refreshed skills list: found {len(skills)} skill(s){error_msg}")

    async def _load_skills(
        self,
        client: "Crow",
        agent_id: str,
        skills_dir: Path,
        skill_ids: list[str],
    ) -> ToolResult:
        """Load skills into the loaded_skills memory block."""
        # Get current loaded_skills block
        try:
            loaded_block = client.agents.blocks.retrieve(
                agent_id=agent_id,
                block_label="loaded_skills",
            )
            current_value = loaded_block.value.strip() if loaded_block.value else ""
        except Exception as e:
            return ToolResult.error(
                f"loaded_skills block not found. This block is required for the Skill tool. "
                f"Error: {e}"
            )

        loaded_skill_ids = get_loaded_skill_ids(current_value)
        results = []

        for skill_id in skill_ids:
            if skill_id in loaded_skill_ids:
                results.append(f'"{skill_id}" already loaded')
                continue

            try:
                skill_content = await self._read_skill_content(skill_id, skills_dir)

                # Replace placeholder if this is the first skill
                if current_value == "[CURRENTLY EMPTY]":
                    current_value = ""

                # Append new skill
                separator = "\n\n---\n\n" if current_value else ""
                current_value = f"{current_value}{separator}# Skill: {skill_id}\n{skill_content}"
                loaded_skill_ids.append(skill_id)
                results.append(f'"{skill_id}" loaded')
            except Exception as e:
                results.append(f'"{skill_id}" failed: {e}')

        # Update the block
        client.agents.blocks.update(
            agent_id=agent_id,
            block_label="loaded_skills",
            value=current_value,
        )

        return ToolResult.success(", ".join(results))

    async def _unload_skills(
        self,
        client: "Crow",
        agent_id: str,
        skill_ids: list[str],
    ) -> ToolResult:
        """Unload skills from the loaded_skills memory block."""
        # Get current loaded_skills block
        try:
            loaded_block = client.agents.blocks.retrieve(
                agent_id=agent_id,
                block_label="loaded_skills",
            )
            current_value = loaded_block.value.strip() if loaded_block.value else ""
        except Exception as e:
            return ToolResult.error(f"loaded_skills block not found. Error: {e}")

        loaded_skill_ids = get_loaded_skill_ids(current_value)
        skill_boundaries = parse_loaded_skills(current_value)
        results = []

        # Sort skills to unload by position (descending) to remove from end first
        skills_to_remove = [
            (skill_id, skill_boundaries[skill_id])
            for skill_id in skill_ids
            if skill_id in skill_boundaries
        ]
        skills_to_remove.sort(key=lambda x: x[1][0], reverse=True)

        for skill_id in skill_ids:
            if skill_id not in loaded_skill_ids:
                results.append(f'"{skill_id}" not loaded')
            else:
                results.append(f'"{skill_id}" unloaded')

        # Remove skills from content (in reverse order to maintain indices)
        for skill_id, (start, end) in skills_to_remove:
            # Check for preceding separator
            sep = "\n\n---\n\n"
            actual_start = start
            if start >= len(sep):
                potential_sep = current_value[start - len(sep) : start]
                if potential_sep == sep:
                    actual_start = start - len(sep)

            current_value = current_value[:actual_start] + current_value[end:]

        # Clean up
        current_value = current_value.strip()
        if not current_value:
            current_value = "[CURRENTLY EMPTY]"

        # Update the block
        client.agents.blocks.update(
            agent_id=agent_id,
            block_label="loaded_skills",
            value=current_value,
        )

        return ToolResult.success(", ".join(results))

    async def _read_skill_content(self, skill_id: str, skills_dir: Path) -> str:
        """Read skill content from SKILL.md file."""
        skill_path = skills_dir / skill_id / "SKILL.md"

        if not skill_path.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_path}")

        return skill_path.read_text()

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        command = args.get("command", "command")
        skills = args.get("skills", [])
        if skills:
            return f"skill {command}: {', '.join(skills)}"
        return f"skill {command}"
