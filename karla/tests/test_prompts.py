"""Unit tests for prompts module.

Tests prompt loading functionality as required by PLAN.md Testing Plan.
"""

import pytest

from karla.prompts import (
    load_system_prompt,
    get_default_system_prompt,
    get_persona,
    list_available_prompts,
    PROMPTS_DIR,
)
from karla.prompts.memory_blocks import (
    load_persona,
    load_memory_block,
    get_default_memory_blocks,
)


class TestPromptLoading:
    """Test prompt loading functions."""

    def test_load_system_prompt_karla_main(self):
        """Test loading the main system prompt."""
        content = load_system_prompt("karla_main")
        assert content is not None
        assert len(content) > 0
        assert "Karla" in content

    def test_load_system_prompt_persona(self):
        """Test loading the persona prompt."""
        content = load_system_prompt("persona")
        assert content is not None
        assert "Karla" in content

    def test_load_system_prompt_not_found(self):
        """Test loading a non-existent prompt raises error."""
        with pytest.raises(FileNotFoundError):
            load_system_prompt("nonexistent_prompt")

    def test_get_default_system_prompt(self):
        """Test getting the default system prompt."""
        content = get_default_system_prompt()
        assert content is not None
        assert len(content) > 0
        # Should contain key sections from PLAN.md spec
        assert "Tone and style" in content
        assert "Professional objectivity" in content
        assert "Task Management" in content
        assert "TodoWrite" in content

    def test_get_persona(self):
        """Test getting the persona content."""
        content = get_persona()
        assert content is not None
        assert "Karla" in content

    def test_list_available_prompts(self):
        """Test listing available prompts."""
        prompts = list_available_prompts()
        assert "karla_main" in prompts
        assert "persona" in prompts

    def test_prompts_dir_exists(self):
        """Test that PROMPTS_DIR exists."""
        assert PROMPTS_DIR.exists()
        assert PROMPTS_DIR.is_dir()


class TestMemoryBlocksModule:
    """Test memory_blocks.py module."""

    def test_load_persona(self):
        """Test loading persona from memory_blocks module."""
        content = load_persona()
        assert content is not None
        assert "Karla" in content

    def test_load_memory_block_persona(self):
        """Test loading persona as memory block."""
        content = load_memory_block("persona")
        assert content is not None
        assert "Karla" in content

    def test_load_memory_block_not_found(self):
        """Test loading non-existent memory block returns None."""
        content = load_memory_block("nonexistent")
        assert content is None

    def test_get_default_memory_blocks(self):
        """Test getting all default memory blocks."""
        blocks = get_default_memory_blocks()
        assert "persona" in blocks
        assert "Karla" in blocks["persona"]


class TestSystemPromptSections:
    """Verify all required sections exist in the system prompt (from PLAN.md spec)."""

    @pytest.fixture
    def system_prompt(self):
        """Load the system prompt once for all tests."""
        return get_default_system_prompt()

    def test_has_identity_section(self, system_prompt):
        """Test that identity and purpose section exists."""
        assert "You are Karla" in system_prompt

    def test_has_tone_and_style_section(self, system_prompt):
        """Test that tone and style section exists."""
        assert "# Tone and style" in system_prompt

    def test_has_professional_objectivity_section(self, system_prompt):
        """Test that professional objectivity section exists."""
        assert "# Professional objectivity" in system_prompt

    def test_has_planning_without_timelines_section(self, system_prompt):
        """Test that planning without timelines section exists."""
        assert "# Planning without timelines" in system_prompt

    def test_has_task_management_section(self, system_prompt):
        """Test that task management section exists."""
        assert "# Task Management" in system_prompt
        assert "TodoWrite" in system_prompt

    def test_has_asking_questions_section(self, system_prompt):
        """Test that asking questions section exists."""
        assert "# Asking questions" in system_prompt
        assert "AskUserQuestion" in system_prompt

    def test_has_doing_tasks_section(self, system_prompt):
        """Test that doing tasks section exists."""
        assert "# Doing tasks" in system_prompt
        assert "over-engineering" in system_prompt

    def test_has_tool_usage_policy_section(self, system_prompt):
        """Test that tool usage policy section exists."""
        assert "# Tool usage policy" in system_prompt

    def test_has_code_references_section(self, system_prompt):
        """Test that code references section exists."""
        assert "# Code References" in system_prompt
        assert "file_path:line_number" in system_prompt
