"""Unit tests for settings persistence.

Tests settings functionality as required by PLAN.md Testing Plan.
"""

import json
import tempfile
from pathlib import Path

import pytest

from karla.settings import (
    SettingsManager,
    GlobalSettings,
    ProjectSettings,
)


class TestGlobalSettings:
    """Test GlobalSettings dataclass."""

    def test_default_values(self):
        """Test default values are None."""
        settings = GlobalSettings()
        assert settings.last_agent is None
        assert settings.default_model is None

    def test_with_values(self):
        """Test with actual values."""
        settings = GlobalSettings(
            last_agent="agent-123",
            default_model="gpt-4"
        )
        assert settings.last_agent == "agent-123"
        assert settings.default_model == "gpt-4"


class TestProjectSettings:
    """Test ProjectSettings dataclass."""

    def test_default_values(self):
        """Test default values are None."""
        settings = ProjectSettings()
        assert settings.last_agent is None

    def test_with_values(self):
        """Test with actual values."""
        settings = ProjectSettings(last_agent="agent-456")
        assert settings.last_agent == "agent-456"


class TestSettingsManager:
    """Test SettingsManager class."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for settings files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            fake_home = tmpdir / "home"
            fake_project = tmpdir / "project"
            fake_home.mkdir()
            fake_project.mkdir()
            yield fake_home, fake_project

    @pytest.fixture
    def manager(self, temp_dirs, monkeypatch):
        """Create SettingsManager with temp directories."""
        fake_home, fake_project = temp_dirs
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        return SettingsManager(project_dir=fake_project)

    def test_empty_state(self, manager):
        """Test empty state returns None."""
        assert manager.get_last_agent() is None
        assert manager.get_default_model() is None

    def test_save_and_get_last_agent(self, manager):
        """Test saving and retrieving last agent."""
        manager.save_last_agent("agent-123")
        assert manager.get_last_agent() == "agent-123"

    def test_project_settings_take_precedence(self, manager, temp_dirs):
        """Test project settings take precedence over global."""
        fake_home, fake_project = temp_dirs

        # Save global setting
        manager.save_last_agent("global-agent")

        # Override with project setting
        local = manager.load_local()
        local.last_agent = "project-agent"
        manager.save_local(local)

        # Project should take precedence
        assert manager.get_last_agent() == "project-agent"

    def test_save_and_get_default_model(self, manager):
        """Test saving and retrieving default model."""
        manager.set_default_model("claude-3-opus")
        assert manager.get_default_model() == "claude-3-opus"

    def test_load_global_creates_default(self, manager):
        """Test load_global returns default when file doesn't exist."""
        settings = manager.load_global()
        assert settings.last_agent is None
        assert settings.default_model is None

    def test_load_local_creates_default(self, manager):
        """Test load_local returns default when file doesn't exist."""
        settings = manager.load_local()
        assert settings.last_agent is None

    def test_save_global_creates_directory(self, manager, temp_dirs):
        """Test save_global creates ~/.karla directory."""
        fake_home, _ = temp_dirs
        settings = GlobalSettings(last_agent="test-agent")
        manager.save_global(settings)

        assert (fake_home / ".karla").exists()
        assert (fake_home / ".karla" / "settings.json").exists()

    def test_save_local_creates_directory(self, manager, temp_dirs):
        """Test save_local creates .karla directory."""
        _, fake_project = temp_dirs
        settings = ProjectSettings(last_agent="test-agent")
        manager.save_local(settings)

        assert (fake_project / ".karla").exists()
        assert (fake_project / ".karla" / "settings.local.json").exists()

    def test_settings_persist_correctly(self, manager, temp_dirs):
        """Test settings are persisted correctly as JSON."""
        fake_home, fake_project = temp_dirs

        manager.save_last_agent("persistent-agent")

        # Read the actual files
        global_file = fake_home / ".karla" / "settings.json"
        local_file = fake_project / ".karla" / "settings.local.json"

        global_data = json.loads(global_file.read_text())
        local_data = json.loads(local_file.read_text())

        assert global_data["last_agent"] == "persistent-agent"
        assert local_data["last_agent"] == "persistent-agent"

    def test_handles_corrupted_files(self, manager, temp_dirs):
        """Test graceful handling of corrupted settings files."""
        _, fake_project = temp_dirs

        # Create corrupted file
        settings_dir = fake_project / ".karla"
        settings_dir.mkdir()
        (settings_dir / "settings.local.json").write_text("not valid json{")

        # Should return default without crashing
        settings = manager.load_local()
        assert settings.last_agent is None
