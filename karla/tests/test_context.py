"""Tests for karla agent context."""

from unittest.mock import MagicMock

import pytest

from karla.context import (
    AgentContext,
    SubagentInfo,
    clear_context,
    get_context,
    set_context,
)


@pytest.fixture
def mock_client():
    """Create a mock Letta client."""
    return MagicMock()


@pytest.fixture
def agent_context(mock_client):
    """Create an agent context for tests."""
    return AgentContext(
        client=mock_client,
        agent_id="agent-test-123",
        working_dir="/tmp/test",
        llm_config={
            "model": "test-model",
            "model_endpoint": "http://localhost:1234/v1",
            "model_endpoint_type": "openai",
            "context_window": 8000,
        },
        embedding_config="ollama/test-embed",
        kv_cache_friendly=True,
    )


class TestAgentContext:
    """Tests for AgentContext."""

    def test_context_creation(self, agent_context, mock_client):
        """Test creating an agent context."""
        assert agent_context.client == mock_client
        assert agent_context.agent_id == "agent-test-123"
        assert agent_context.working_dir == "/tmp/test"
        assert agent_context.kv_cache_friendly is True
        assert agent_context.llm_config["model"] == "test-model"

    def test_register_subagent(self, agent_context):
        """Test registering a subagent."""
        tracking_id = agent_context.register_subagent(
            agent_id="agent-sub-456",
            subagent_type="Explore",
            description="Find test files",
        )

        assert tracking_id.startswith("subagent-")

        subagent = agent_context.get_subagent(tracking_id)
        assert subagent is not None
        assert subagent.agent_id == "agent-sub-456"
        assert subagent.subagent_type == "Explore"
        assert subagent.description == "Find test files"
        assert subagent.status == "running"

    def test_complete_subagent(self, agent_context):
        """Test marking a subagent as completed."""
        tracking_id = agent_context.register_subagent(
            agent_id="agent-sub-456",
            subagent_type="Explore",
            description="Find test files",
        )

        agent_context.complete_subagent(tracking_id, "Found 5 test files")

        subagent = agent_context.get_subagent(tracking_id)
        assert subagent.status == "completed"
        assert subagent.result == "Found 5 test files"

    def test_fail_subagent(self, agent_context):
        """Test marking a subagent as failed."""
        tracking_id = agent_context.register_subagent(
            agent_id="agent-sub-456",
            subagent_type="Explore",
            description="Find test files",
        )

        agent_context.fail_subagent(tracking_id, "Connection timeout")

        subagent = agent_context.get_subagent(tracking_id)
        assert subagent.status == "error"
        assert subagent.error == "Connection timeout"

    def test_list_subagents(self, agent_context):
        """Test listing all subagents."""
        agent_context.register_subagent(
            agent_id="agent-sub-1",
            subagent_type="Explore",
            description="Task 1",
        )
        agent_context.register_subagent(
            agent_id="agent-sub-2",
            subagent_type="Plan",
            description="Task 2",
        )

        subagents = agent_context.list_subagents()
        assert len(subagents) == 2

    def test_get_nonexistent_subagent(self, agent_context):
        """Test getting a subagent that doesn't exist."""
        subagent = agent_context.get_subagent("nonexistent-id")
        assert subagent is None


class TestGlobalContext:
    """Tests for global context management."""

    def teardown_method(self):
        """Clean up after each test."""
        clear_context()

    def test_set_and_get_context(self, agent_context):
        """Test setting and getting global context."""
        set_context(agent_context)

        ctx = get_context()
        assert ctx == agent_context
        assert ctx.agent_id == "agent-test-123"

    def test_get_context_without_setting(self):
        """Test getting context when none is set."""
        clear_context()

        with pytest.raises(RuntimeError, match="No agent context set"):
            get_context()

    def test_clear_context(self, agent_context):
        """Test clearing the global context."""
        set_context(agent_context)
        clear_context()

        with pytest.raises(RuntimeError):
            get_context()


class TestSubagentInfo:
    """Tests for SubagentInfo dataclass."""

    def test_subagent_info_creation(self):
        """Test creating SubagentInfo."""
        info = SubagentInfo(
            id="subagent-abc123",
            agent_id="agent-456",
            subagent_type="Explore",
            description="Search codebase",
            status="running",
        )

        assert info.id == "subagent-abc123"
        assert info.agent_id == "agent-456"
        assert info.subagent_type == "Explore"
        assert info.description == "Search codebase"
        assert info.status == "running"
        assert info.result is None
        assert info.error is None
