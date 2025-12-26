"""Integration tests for karla with a real Letta server.

These tests require a running Letta server at localhost:8283.
Skip with: pytest tests/test_integration.py -k "not integration"
Or run only integration: pytest tests/test_integration.py -m integration

Environment variables can override defaults:
- LETTA_URL: Letta server URL (default: http://localhost:8283)
- LETTA_MODEL: Model path or name for LLM
- LETTA_MODEL_ENDPOINT: LLM endpoint URL
- LETTA_EMBEDDING: Embedding model
"""

import os

import pytest

# Default LLM config for local testing
DEFAULT_MODEL = (
    "/home/thomas-wood/.cache/llama.cpp/"
    "lmstudio-community_Qwen3-Coder-30B-A3B-Instruct-GGUF_"
    "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
)
DEFAULT_MODEL_ENDPOINT = "http://coast-after-3:1234/v1"
DEFAULT_EMBEDDING = "ollama/mxbai-embed-large:latest"

# Check if Letta server is available
LETTA_URL = os.environ.get("LETTA_URL", "http://localhost:8283")
LETTA_MODEL = os.environ.get("LETTA_MODEL", DEFAULT_MODEL)
LETTA_MODEL_ENDPOINT = os.environ.get("LETTA_MODEL_ENDPOINT", DEFAULT_MODEL_ENDPOINT)
LETTA_EMBEDDING = os.environ.get("LETTA_EMBEDDING", DEFAULT_EMBEDDING)


def letta_server_available():
    """Check if Letta server is running."""
    try:
        import httpx

        response = httpx.get(f"{LETTA_URL}/v1/health/", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_llm_config():
    """Get LLM config."""
    return {
        "model": LETTA_MODEL,
        "model_endpoint": LETTA_MODEL_ENDPOINT,
        "model_endpoint_type": "openai",
        "context_window": 119000,
    }


# Skip all tests in this module if server not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not letta_server_available(), reason=f"Letta server not available at {LETTA_URL}"
    ),
]


@pytest.fixture
def letta_client():
    """Create a Letta client with no timeout for local LLMs."""
    from letta_client import Letta

    return Letta(base_url=LETTA_URL, timeout=None)


@pytest.fixture
def llm_config():
    """Get LLM config."""
    return get_llm_config()


@pytest.fixture
def test_agent(letta_client, llm_config):
    """Create a test agent and clean up after."""
    agent = letta_client.agents.create(
        name="karla-test-agent",
        system="You are a test agent. Respond briefly.",
        llm_config=llm_config,
        embedding=LETTA_EMBEDDING,
        include_base_tools=True,
        kv_cache_friendly=True,
    )
    yield agent
    # Cleanup
    try:
        letta_client.agents.delete(agent.id)
    except Exception:
        pass


class TestLettaConnection:
    """Test basic Letta server connectivity."""

    def test_health_check(self, letta_client):
        """Test that we can connect to Letta server."""
        health = letta_client.health()
        assert health is not None

    def test_list_agents(self, letta_client):
        """Test listing agents."""
        agents = letta_client.agents.list()
        # Should return a list (may be empty)
        assert isinstance(list(agents), list)


class TestAgentCreation:
    """Test creating agents with karla-compatible settings."""

    def test_create_agent_with_kv_cache_friendly(self, letta_client, llm_config):
        """Test creating an agent with kv_cache_friendly flag."""
        agent = letta_client.agents.create(
            name="karla-kv-test",
            system="You are a test agent.",
            llm_config=llm_config,
            embedding=LETTA_EMBEDDING,
            kv_cache_friendly=True,
            include_base_tools=True,
        )

        try:
            assert agent.id is not None
            assert agent.name == "karla-kv-test"
            # Verify kv_cache_friendly was set
            retrieved = letta_client.agents.retrieve(agent.id)
            assert retrieved.kv_cache_friendly is True
        finally:
            letta_client.agents.delete(agent.id)

    def test_create_agent_with_memory_blocks(self, letta_client, llm_config):
        """Test creating an agent with custom memory blocks."""
        agent = letta_client.agents.create(
            name="karla-memory-test",
            system="You are a test agent with memory.",
            llm_config=llm_config,
            embedding=LETTA_EMBEDDING,
            kv_cache_friendly=True,
            memory_blocks=[
                {"label": "persona", "value": "I am a helpful assistant."},
                {"label": "human", "value": "The user is a developer."},
            ],
        )

        try:
            assert agent.id is not None
            # Verify memory blocks
            blocks = list(letta_client.agents.blocks.list(agent.id))
            labels = [b.label for b in blocks]
            assert "persona" in labels
            assert "human" in labels
        finally:
            letta_client.agents.delete(agent.id)


class TestMemoryTools:
    """Test memory-related tools work with kv_cache_friendly."""

    def test_memory_read_tool_available(self, letta_client, test_agent):
        """Test that memory_read tool is available."""
        tools = list(letta_client.agents.tools.list(test_agent.id))
        tool_names = [t.name for t in tools]
        assert "memory_read" in tool_names

    def test_memory_tools_available(self, letta_client, test_agent):
        """Test that memory tools are available."""
        tools = list(letta_client.agents.tools.list(test_agent.id))
        tool_names = [t.name for t in tools]
        # kv-cache-friendly branch uses memory_insert/memory_replace
        assert "memory_insert" in tool_names
        assert "memory_replace" in tool_names


class TestKarlaConfig:
    """Test karla config with real Letta client."""

    def test_create_client_from_config(self):
        """Test creating a Letta client from karla config."""
        from karla.config import KarlaConfig, create_client

        config = KarlaConfig.from_dict(
            {
                "server": {"base_url": LETTA_URL, "timeout": None},
                "llm": {"model": "test", "model_endpoint": "http://localhost:1234/v1"},
                "embedding": {"model": "test-embed"},
            }
        )

        client = create_client(config)
        # Should be able to call health
        health = client.health()
        assert health is not None

    def test_config_timeout_none_means_no_timeout(self):
        """Test that timeout=None creates client with no timeout."""
        from karla.config import KarlaConfig, create_client

        config = KarlaConfig.from_dict(
            {
                "server": {"base_url": LETTA_URL},  # timeout not specified = None
                "llm": {"model": "test", "model_endpoint": "http://localhost:1234/v1"},
                "embedding": {"model": "test-embed"},
            }
        )

        assert config.server.timeout is None

        client = create_client(config)
        # Client should work
        health = client.health()
        assert health is not None


class TestAgentContext:
    """Test karla AgentContext with real Letta."""

    def test_context_setup(self, letta_client, test_agent):
        """Test setting up agent context."""
        from karla import AgentContext, clear_context, get_context, set_context

        ctx = AgentContext(
            client=letta_client,
            agent_id=test_agent.id,
            working_dir="/tmp",
            kv_cache_friendly=True,
        )

        set_context(ctx)

        try:
            retrieved = get_context()
            assert retrieved.agent_id == test_agent.id
            assert retrieved.kv_cache_friendly is True
        finally:
            clear_context()
