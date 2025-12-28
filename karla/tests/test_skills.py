"""Unit tests for skills module.

Tests skill discovery functionality as required by PLAN.md Testing Plan.
"""

import tempfile
from pathlib import Path

import pytest

from karla.skills import (
    Skill,
    parse_yaml_frontmatter,
    strip_frontmatter,
    discover_skill,
    discover_skills,
    find_skills_directories,
    discover_all_skills,
    format_skills_for_memory,
    format_loaded_skills,
    get_skill_by_id,
)


class TestYamlFrontmatter:
    """Test YAML frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = """---
name: My Skill
description: A helpful skill
---

# Skill Content
"""
        metadata = parse_yaml_frontmatter(content)
        assert metadata["name"] == "My Skill"
        assert metadata["description"] == "A helpful skill"

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just Markdown\n\nNo frontmatter here."
        metadata = parse_yaml_frontmatter(content)
        assert metadata == {}

    def test_parse_quoted_values(self):
        """Test parsing frontmatter with quoted values."""
        content = """---
name: "Quoted Name"
description: 'Single Quoted'
---

Content
"""
        metadata = parse_yaml_frontmatter(content)
        assert metadata["name"] == "Quoted Name"
        assert metadata["description"] == "Single Quoted"

    def test_strip_frontmatter(self):
        """Test stripping frontmatter from content."""
        content = """---
name: Test
---

# The Real Content

This is the body.
"""
        stripped = strip_frontmatter(content)
        assert stripped.startswith("# The Real Content")
        assert "---" not in stripped

    def test_strip_no_frontmatter(self):
        """Test stripping when no frontmatter exists."""
        content = "# Just Content\n\nNo frontmatter."
        stripped = strip_frontmatter(content)
        assert stripped == content


class TestSkillDataclass:
    """Test Skill dataclass."""

    def test_skill_creation(self):
        """Test creating a Skill instance."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            path=Path("/tmp/test"),
            content="---\nname: Test\n---\n\n# Content",
        )
        assert skill.id == "test-skill"
        assert skill.name == "Test Skill"
        assert skill.description == "A test skill"

    def test_skill_prompt_property(self):
        """Test the prompt property strips frontmatter."""
        skill = Skill(
            id="test",
            name="Test",
            description="Test",
            path=Path("/tmp"),
            content="---\nname: Test\n---\n\n# The Prompt",
        )
        assert skill.prompt.startswith("# The Prompt")
        assert "---" not in skill.prompt


class TestSkillDiscovery:
    """Test skill discovery functions."""

    @pytest.fixture
    def skills_dir(self):
        """Create a temporary skills directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir) / ".skills"
            skills_path.mkdir()

            # Create a valid skill
            commit_skill = skills_path / "commit"
            commit_skill.mkdir()
            (commit_skill / "SKILL.md").write_text("""---
name: Commit Helper
description: Helps format git commits
---

# Commit Helper

Use this skill for git commits.
""")

            # Create another skill
            review_skill = skills_path / "review-pr"
            review_skill.mkdir()
            (review_skill / "SKILL.md").write_text("""---
name: PR Review
description: Reviews pull requests
---

# PR Review

Use this for reviewing PRs.
""")

            yield skills_path

    def test_discover_skill(self, skills_dir):
        """Test discovering a single skill."""
        skill_path = skills_dir / "commit" / "SKILL.md"
        skill = discover_skill(skill_path)

        assert skill is not None
        assert skill.id == "commit"
        assert skill.name == "Commit Helper"
        assert skill.description == "Helps format git commits"

    def test_discover_skill_invalid_path(self):
        """Test discovering skill with invalid path."""
        skill = discover_skill(Path("/nonexistent/SKILL.md"))
        assert skill is None

    def test_discover_skill_wrong_filename(self, skills_dir):
        """Test discovering skill with wrong filename."""
        wrong_file = skills_dir / "commit" / "README.md"
        wrong_file.write_text("Not a skill")
        skill = discover_skill(wrong_file)
        assert skill is None

    def test_discover_skills(self, skills_dir):
        """Test discovering all skills in a directory."""
        skills = discover_skills(skills_dir)
        assert len(skills) == 2

        skill_ids = {s.id for s in skills}
        assert "commit" in skill_ids
        assert "review-pr" in skill_ids

    def test_discover_skills_empty_dir(self):
        """Test discovering skills in empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir) / ".skills"
            empty_dir.mkdir()
            skills = discover_skills(empty_dir)
            assert skills == []

    def test_discover_skills_nonexistent_dir(self):
        """Test discovering skills in nonexistent directory."""
        skills = discover_skills(Path("/nonexistent/dir"))
        assert skills == []


class TestSkillsFormatting:
    """Test skill formatting functions."""

    @pytest.fixture
    def sample_skills(self):
        """Create sample skills for formatting tests."""
        return [
            Skill(
                id="commit",
                name="Commit",
                description="Git commit helper",
                path=Path("/tmp/commit"),
                content="# Commit\n\nUse for commits.",
            ),
            Skill(
                id="review",
                name="Review",
                description="Code review helper",
                path=Path("/tmp/review"),
                content="# Review\n\nUse for reviews.",
            ),
        ]

    def test_format_skills_for_memory(self, sample_skills):
        """Test formatting skills for memory block."""
        formatted = format_skills_for_memory(sample_skills)
        assert "# Available Skills" in formatted
        assert "**commit**" in formatted
        assert "**review**" in formatted
        assert "Git commit helper" in formatted

    def test_format_skills_for_memory_empty(self):
        """Test formatting empty skills list."""
        formatted = format_skills_for_memory([])
        assert "No skills configured" in formatted

    def test_format_loaded_skills(self, sample_skills):
        """Test formatting loaded skills."""
        formatted = format_loaded_skills(sample_skills)
        assert "# Loaded Skills" in formatted
        assert "## Commit" in formatted
        assert "## Review" in formatted

    def test_format_loaded_skills_empty(self):
        """Test formatting empty loaded skills."""
        formatted = format_loaded_skills([])
        assert "No skills currently loaded" in formatted


class TestSkillLookup:
    """Test skill lookup functions."""

    @pytest.fixture
    def skills(self):
        """Create skills for lookup tests."""
        return [
            Skill(id="skill-1", name="Skill 1", description="", path=Path("/tmp"), content=""),
            Skill(id="skill-2", name="Skill 2", description="", path=Path("/tmp"), content=""),
        ]

    def test_get_skill_by_id(self, skills):
        """Test finding skill by ID."""
        skill = get_skill_by_id(skills, "skill-1")
        assert skill is not None
        assert skill.id == "skill-1"
        assert skill.name == "Skill 1"

    def test_get_skill_by_id_not_found(self, skills):
        """Test finding non-existent skill."""
        skill = get_skill_by_id(skills, "nonexistent")
        assert skill is None


class TestFindSkillsDirectories:
    """Test finding skills directories."""

    def test_find_skills_directories(self, monkeypatch):
        """Test finding skills directories in hierarchy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            project_dir = tmpdir / "project" / "subdir"
            project_dir.mkdir(parents=True)

            # Create .skills in parent
            skills_dir = tmpdir / "project" / ".skills"
            skills_dir.mkdir()

            monkeypatch.setattr(Path, "home", lambda: tmpdir)

            dirs = find_skills_directories(project_dir)
            assert len(dirs) >= 1
            assert skills_dir in dirs
