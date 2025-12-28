"""Skills system for Karla agents.

Skills are reusable prompts/instructions that can be loaded into agent memory.
They're stored in .skills/ directories with SKILL.md files containing
YAML frontmatter and markdown content.

Directory structure:
    .skills/
    ├── commit/
    │   └── SKILL.md
    ├── review-pr/
    │   └── SKILL.md
    └── ...
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A loadable skill for the agent."""
    id: str
    name: str
    description: str
    path: Path
    content: str

    @property
    def prompt(self) -> str:
        """Get the skill content without frontmatter."""
        return strip_frontmatter(self.content)


def parse_yaml_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content potentially starting with ---

    Returns:
        Dictionary of frontmatter values, empty if none found
    """
    if not content.startswith("---"):
        return {}

    # Find the closing ---
    lines = content.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}

    # Parse YAML between the markers
    yaml_content = "\n".join(lines[1:end_idx])

    # Simple YAML parsing (key: value pairs)
    result = {}
    for line in yaml_content.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")

    return result


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content.

    Args:
        content: Markdown content potentially starting with ---

    Returns:
        Content without frontmatter
    """
    if not content.startswith("---"):
        return content

    lines = content.split("\n")
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1:]).lstrip()

    return content


def discover_skill(skill_path: Path) -> Optional[Skill]:
    """Discover a single skill from a SKILL.md file.

    Args:
        skill_path: Path to SKILL.md file

    Returns:
        Skill instance or None if invalid
    """
    if not skill_path.exists() or skill_path.name != "SKILL.md":
        return None

    try:
        content = skill_path.read_text()
        metadata = parse_yaml_frontmatter(content)

        skill_id = skill_path.parent.name
        name = metadata.get("name", skill_id)
        description = metadata.get("description", "")

        return Skill(
            id=skill_id,
            name=name,
            description=description,
            path=skill_path.parent,
            content=content,
        )
    except Exception as e:
        logger.warning("Failed to load skill %s: %s", skill_path, e)
        return None


def discover_skills(skills_dir: Path) -> list[Skill]:
    """Discover all skills in a directory.

    Args:
        skills_dir: Path to .skills directory

    Returns:
        List of discovered Skill instances
    """
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []

    skills = []
    for skill_file in skills_dir.glob("*/SKILL.md"):
        skill = discover_skill(skill_file)
        if skill:
            skills.append(skill)

    logger.info("Discovered %d skills in %s", len(skills), skills_dir)
    return skills


def find_skills_directories(start_dir: Path) -> list[Path]:
    """Find all .skills directories in the project hierarchy.

    Searches:
    1. Current directory
    2. Parent directories up to home
    3. ~/.karla/skills (global skills)

    Args:
        start_dir: Directory to start searching from

    Returns:
        List of existing .skills directories
    """
    dirs = []

    # Search up the directory tree
    current = start_dir.resolve()
    home = Path.home()

    while current != current.parent and current >= home:
        skills_dir = current / ".skills"
        if skills_dir.exists() and skills_dir.is_dir():
            dirs.append(skills_dir)
        current = current.parent

    # Add global skills directory
    global_skills = home / ".karla" / "skills"
    if global_skills.exists() and global_skills.is_dir():
        dirs.append(global_skills)

    return dirs


def discover_all_skills(start_dir: Path) -> list[Skill]:
    """Discover all available skills from all search paths.

    Args:
        start_dir: Directory to start searching from

    Returns:
        List of all discovered skills (deduplicated by id)
    """
    seen_ids = set()
    all_skills = []

    for skills_dir in find_skills_directories(start_dir):
        for skill in discover_skills(skills_dir):
            if skill.id not in seen_ids:
                seen_ids.add(skill.id)
                all_skills.append(skill)

    return all_skills


def format_skills_for_memory(skills: list[Skill]) -> str:
    """Format skills list for the skills memory block.

    Args:
        skills: List of Skill instances

    Returns:
        Formatted markdown for the memory block
    """
    if not skills:
        return "# Available Skills\n\nNo skills configured."

    lines = ["# Available Skills", ""]
    for skill in skills:
        desc = skill.description or "No description"
        lines.append(f"- **{skill.id}**: {desc}")

    return "\n".join(lines)


def format_loaded_skills(skills: list[Skill]) -> str:
    """Format loaded skills for the loaded_skills memory block.

    Args:
        skills: List of currently loaded Skill instances

    Returns:
        Formatted markdown for the memory block
    """
    if not skills:
        return "# Loaded Skills\n\nNo skills currently loaded."

    lines = ["# Loaded Skills", ""]
    for skill in skills:
        lines.append(f"## {skill.name}")
        lines.append("")
        lines.append(skill.prompt)
        lines.append("")

    return "\n".join(lines)


def get_skill_by_id(skills: list[Skill], skill_id: str) -> Optional[Skill]:
    """Find a skill by its ID.

    Args:
        skills: List of skills to search
        skill_id: ID to find

    Returns:
        Skill instance or None
    """
    for skill in skills:
        if skill.id == skill_id:
            return skill
    return None
