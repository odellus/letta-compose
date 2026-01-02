"""Integration tests for karla with a real Crow server.

These tests require a running Crow server at localhost:8283.
Skip with: pytest tests/test_integration.py -k "not integration"
Or run only integration: pytest tests/test_integration.py -m integration

Environment variables can override defaults:
- CROW_URL: Crow server URL (default: http://localhost:8283)
- CROW_MODEL: Model path or name for LLM
- CROW_MODEL_ENDPOINT: LLM endpoint URL
- CROW_EMBEDDING: Embedding model
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

# Check if Crow server is available
CROW_URL = os.environ.get("CROW_URL", "http://localhost:8283")
CROW_MODEL = os.environ.get("CROW_MODEL", DEFAULT_MODEL)
CROW_MODEL_ENDPOINT = os.environ.get("CROW_MODEL_ENDPOINT", DEFAULT_MODEL_ENDPOINT)
CROW_EMBEDDING = os.environ.get("CROW_EMBEDDING", DEFAULT_EMBEDDING)


def crow_server_available():
    """Check if Crow server is running."""
    try:
        import httpx

        response = httpx.get(f"{CROW_URL}/v1/health/", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_llm_config():
    """Get LLM config."""
    return {
        "model": CROW_MODEL,
        "model_endpoint": CROW_MODEL_ENDPOINT,
        "model_endpoint_type": "openai",
        "context_window": 119000,
    }


# Skip all tests in this module if server not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not crow_server_available(), reason=f"Crow server not available at {CROW_URL}"
    ),
]


@pytest.fixture
def crow_client():
    """Create a Crow client with no timeout for local LLMs."""
    from crow_client import Crow

    return Crow(base_url=CROW_URL, timeout=None)


@pytest.fixture
def llm_config():
    """Get LLM config."""
    return get_llm_config()


@pytest.fixture
def test_agent(crow_client, llm_config):
    """Create a test agent and clean up after."""
    agent = crow_client.agents.create(
        name="karla-test-agent",
        system="You are a test agent. Respond briefly.",
        llm_config=llm_config,
        embedding=CROW_EMBEDDING,
        include_base_tools=True,
        kv_cache_friendly=True,
    )
    yield agent
    # Cleanup
    try:
        crow_client.agents.delete(agent.id)
    except Exception:
        pass


class TestCrowConnection:
    """Test basic Crow server connectivity."""

    def test_health_check(self, crow_client):
        """Test that we can connect to Crow server."""
        health = crow_client.health()
        assert health is not None

    def test_list_agents(self, crow_client):
        """Test listing agents."""
        agents = crow_client.agents.list()
        # Should return a list (may be empty)
        assert isinstance(list(agents), list)


class TestAgentCreation:
    """Test creating agents with karla-compatible settings."""

    def test_create_agent_with_kv_cache_friendly(self, crow_client, llm_config):
        """Test creating an agent with kv_cache_friendly flag."""
        agent = crow_client.agents.create(
            name="karla-kv-test",
            system="You are a test agent.",
            llm_config=llm_config,
            embedding=CROW_EMBEDDING,
            kv_cache_friendly=True,
            include_base_tools=True,
        )

        try:
            assert agent.id is not None
            assert agent.name == "karla-kv-test"
            # Verify kv_cache_friendly was set
            retrieved = crow_client.agents.retrieve(agent.id)
            assert retrieved.kv_cache_friendly is True
        finally:
            crow_client.agents.delete(agent.id)

    def test_create_agent_with_memory_blocks(self, crow_client, llm_config):
        """Test creating an agent with custom memory blocks."""
        agent = crow_client.agents.create(
            name="karla-memory-test",
            system="You are a test agent with memory.",
            llm_config=llm_config,
            embedding=CROW_EMBEDDING,
            kv_cache_friendly=True,
            memory_blocks=[
                {"label": "persona", "value": "I am a helpful assistant."},
                {"label": "human", "value": "The user is a developer."},
            ],
        )

        try:
            assert agent.id is not None
            # Verify memory blocks
            blocks = list(crow_client.agents.blocks.list(agent.id))
            labels = [b.label for b in blocks]
            assert "persona" in labels
            assert "human" in labels
        finally:
            crow_client.agents.delete(agent.id)


class TestMemoryTools:
    """Test memory-related tools work with kv_cache_friendly."""

    def test_memory_read_tool_available(self, crow_client, test_agent):
        """Test that memory_read tool is available."""
        tools = list(crow_client.agents.tools.list(test_agent.id))
        tool_names = [t.name for t in tools]
        assert "memory_read" in tool_names

    def test_memory_tools_available(self, crow_client, test_agent):
        """Test that memory tools are available."""
        tools = list(crow_client.agents.tools.list(test_agent.id))
        tool_names = [t.name for t in tools]
        # kv-cache-friendly branch uses memory_insert/memory_replace
        assert "memory_insert" in tool_names
        assert "memory_replace" in tool_names


class TestKarlaConfig:
    """Test karla config with real Crow client."""

    def test_create_client_from_config(self):
        """Test creating a Crow client from karla config."""
        from karla.config import KarlaConfig, create_client

        config = KarlaConfig.from_dict(
            {
                "server": {"base_url": CROW_URL, "timeout": None},
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
                "server": {"base_url": CROW_URL},  # timeout not specified = None
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
    """Test karla AgentContext with real Crow."""

    def test_context_setup(self, crow_client, test_agent):
        """Test setting up agent context."""
        from karla import AgentContext, clear_context, get_context, set_context

        ctx = AgentContext(
            client=crow_client,
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


class TestHeadlessMode:
    """Test CLI headless mode functionality."""

    def test_headless_creates_agent(self, crow_client, llm_config):
        """Test headless mode creates agent and runs loop."""
        import asyncio
        import tempfile

        from karla.config import KarlaConfig
        from karla.headless import run_headless, OutputFormat

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.from_dict({
                "server": {"base_url": CROW_URL, "timeout": None},
                "llm": llm_config,
                "embedding": {"model": CROW_EMBEDDING},
            })

            # Run headless with a simple prompt
            response, agent_id = asyncio.get_event_loop().run_until_complete(
                run_headless(
                    prompt="Say hello",
                    config=config,
                    working_dir=tmpdir,
                    force_new=True,
                )
            )

            try:
                # Verify agent was created
                assert agent_id is not None
                agent = crow_client.agents.retrieve(agent_id)
                assert agent.name.startswith("karla-")

                # Verify response was received
                assert response is not None
                assert response.iterations >= 0
            finally:
                # Cleanup
                try:
                    crow_client.agents.delete(agent_id)
                except Exception:
                    pass

    def test_headless_output_formats(self, crow_client, llm_config):
        """Test headless mode output format options."""
        import asyncio
        import tempfile

        from karla.config import KarlaConfig
        from karla.headless import run_headless, format_headless_output
        from karla.agent_loop import OutputFormat

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.from_dict({
                "server": {"base_url": CROW_URL, "timeout": None},
                "llm": llm_config,
                "embedding": {"model": CROW_EMBEDDING},
            })

            response, agent_id = asyncio.get_event_loop().run_until_complete(
                run_headless(
                    prompt="Say hello",
                    config=config,
                    working_dir=tmpdir,
                    force_new=True,
                )
            )

            try:
                # Test text format
                text_output = format_headless_output(response, OutputFormat.TEXT)
                assert isinstance(text_output, str)

                # Test JSON format
                json_output = format_headless_output(response, OutputFormat.JSON)
                import json
                parsed = json.loads(json_output)
                assert "text" in parsed
                assert "tool_results" in parsed
                assert "iterations" in parsed
            finally:
                try:
                    crow_client.agents.delete(agent_id)
                except Exception:
                    pass


class TestAgentSessionContinuity:
    """Test agent session continuity (E2E test)."""

    def test_continue_last_agent(self, crow_client, llm_config):
        """Test continuing with last agent maintains session."""
        import asyncio
        import tempfile

        from karla.config import KarlaConfig
        from karla.headless import run_headless
        from karla.settings import SettingsManager

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.from_dict({
                "server": {"base_url": CROW_URL, "timeout": None},
                "llm": llm_config,
                "embedding": {"model": CROW_EMBEDDING},
            })

            # First run - create new agent
            response1, agent_id1 = asyncio.get_event_loop().run_until_complete(
                run_headless(
                    prompt="Remember the code word: BANANA",
                    config=config,
                    working_dir=tmpdir,
                    force_new=True,
                )
            )

            try:
                # Verify agent was saved
                settings = SettingsManager(project_dir=tmpdir)
                saved_id = settings.get_last_agent()
                assert saved_id == agent_id1

                # Second run - continue last agent
                response2, agent_id2 = asyncio.get_event_loop().run_until_complete(
                    run_headless(
                        prompt="What was the code word?",
                        config=config,
                        working_dir=tmpdir,
                        continue_last=True,
                    )
                )

                # Should use same agent
                assert agent_id2 == agent_id1

            finally:
                # Cleanup
                try:
                    crow_client.agents.delete(agent_id1)
                except Exception:
                    pass

    def test_force_new_creates_different_agent(self, crow_client, llm_config):
        """Test force_new creates a new agent instead of continuing."""
        import asyncio
        import tempfile

        from karla.config import KarlaConfig
        from karla.headless import run_headless

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.from_dict({
                "server": {"base_url": CROW_URL, "timeout": None},
                "llm": llm_config,
                "embedding": {"model": CROW_EMBEDDING},
            })

            # First run
            _, agent_id1 = asyncio.get_event_loop().run_until_complete(
                run_headless(
                    prompt="Hello",
                    config=config,
                    working_dir=tmpdir,
                    force_new=True,
                )
            )

            try:
                # Second run with force_new
                _, agent_id2 = asyncio.get_event_loop().run_until_complete(
                    run_headless(
                        prompt="Hello again",
                        config=config,
                        working_dir=tmpdir,
                        force_new=True,
                    )
                )

                try:
                    # Should be different agents
                    assert agent_id2 != agent_id1
                finally:
                    try:
                        crow_client.agents.delete(agent_id2)
                    except Exception:
                        pass
            finally:
                try:
                    crow_client.agents.delete(agent_id1)
                except Exception:
                    pass

    def test_explicit_agent_id(self, crow_client, test_agent, llm_config):
        """Test using explicit agent ID."""
        import asyncio
        import tempfile

        from karla.config import KarlaConfig
        from karla.headless import run_headless

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KarlaConfig.from_dict({
                "server": {"base_url": CROW_URL, "timeout": None},
                "llm": llm_config,
                "embedding": {"model": CROW_EMBEDDING},
            })

            # Run with explicit agent ID
            _, returned_id = asyncio.get_event_loop().run_until_complete(
                run_headless(
                    prompt="Hello",
                    config=config,
                    working_dir=tmpdir,
                    agent_id=test_agent.id,
                )
            )

            # Should use the specified agent
            assert returned_id == test_agent.id
