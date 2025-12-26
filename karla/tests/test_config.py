"""Tests for karla configuration."""

import tempfile
from pathlib import Path

import pytest

from karla.config import (
    AgentDefaults,
    EmbeddingConfig,
    KarlaConfig,
    LLMConfig,
    ServerConfig,
    load_config,
)


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_to_dict(self):
        """Test converting LLM config to dict."""
        config = LLMConfig(
            model="/path/to/model.gguf",
            model_endpoint="http://localhost:1234/v1",
            model_endpoint_type="openai",
            context_window=32000,
        )

        result = config.to_dict()

        assert result["model"] == "/path/to/model.gguf"
        assert result["model_endpoint"] == "http://localhost:1234/v1"
        assert result["model_endpoint_type"] == "openai"
        assert result["context_window"] == 32000


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig."""

    def test_to_string(self):
        """Test converting embedding config to string."""
        config = EmbeddingConfig(model="ollama/mxbai-embed-large:latest")
        assert config.to_string() == "ollama/mxbai-embed-large:latest"


class TestKarlaConfig:
    """Tests for KarlaConfig."""

    def test_from_dict(self):
        """Test creating config from dict."""
        data = {
            "llm": {
                "model": "/path/to/model.gguf",
                "model_endpoint": "http://localhost:1234/v1",
                "context_window": 32000,
            },
            "embedding": {
                "model": "ollama/test-embed",
            },
            "server": {
                "base_url": "http://localhost:9999",
            },
            "agent_defaults": {
                "kv_cache_friendly": False,
            },
        }

        config = KarlaConfig.from_dict(data)

        assert config.llm.model == "/path/to/model.gguf"
        assert config.llm.context_window == 32000
        assert config.embedding.model == "ollama/test-embed"
        assert config.server.base_url == "http://localhost:9999"
        assert config.agent_defaults.kv_cache_friendly is False

    def test_from_dict_defaults(self):
        """Test that defaults are applied for missing fields."""
        data = {
            "llm": {
                "model": "test-model",
                "model_endpoint": "http://localhost:1234/v1",
            },
            "embedding": {
                "model": "test-embed",
            },
        }

        config = KarlaConfig.from_dict(data)

        assert config.llm.model_endpoint_type == "openai"
        assert config.llm.context_window == 8000
        assert config.server.base_url == "http://localhost:8283"
        assert config.agent_defaults.kv_cache_friendly is True

    def test_from_yaml(self):
        """Test loading config from YAML file."""
        yaml_content = """
llm:
  model: /path/to/model.gguf
  model_endpoint: http://localhost:1234/v1
  context_window: 16000

embedding:
  model: ollama/embed-model

server:
  base_url: http://localhost:8000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = KarlaConfig.from_yaml(temp_path)

            assert config.llm.model == "/path/to/model.gguf"
            assert config.llm.context_window == 16000
            assert config.embedding.model == "ollama/embed-model"
            assert config.server.base_url == "http://localhost:8000"
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_not_found(self):
        """Test error when YAML file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            KarlaConfig.from_yaml("/nonexistent/path/config.yaml")

    def test_find_and_load_current_dir(self):
        """Test finding config in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "karla.yaml"
            config_path.write_text("""
llm:
  model: test-model
  model_endpoint: http://localhost:1234/v1
embedding:
  model: test-embed
""")

            config = KarlaConfig.find_and_load(tmpdir)

            assert config is not None
            assert config.llm.model == "test-model"

    def test_find_and_load_dot_karla_dir(self):
        """Test finding config in .karla directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            karla_dir = Path(tmpdir) / ".karla"
            karla_dir.mkdir()
            config_path = karla_dir / "config.yaml"
            config_path.write_text("""
llm:
  model: dot-karla-model
  model_endpoint: http://localhost:1234/v1
embedding:
  model: test-embed
""")

            config = KarlaConfig.find_and_load(tmpdir)

            assert config is not None
            assert config.llm.model == "dot-karla-model"

    def test_find_and_load_not_found(self):
        """Test when no config file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.find_and_load(tmpdir)
            assert config is None


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_explicit_path(self):
        """Test loading from explicit path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
llm:
  model: explicit-model
  model_endpoint: http://localhost:1234/v1
embedding:
  model: test-embed
""")
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.llm.model == "explicit-model"
        finally:
            Path(temp_path).unlink()

    def test_load_not_found(self):
        """Test error when no config found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to empty dir where no config exists
            import os

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with pytest.raises(FileNotFoundError, match="No karla config found"):
                    load_config()
            finally:
                os.chdir(old_cwd)
