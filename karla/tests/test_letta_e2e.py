"""Real Letta end-to-end tests for karla.

These tests:
1. Connect to a running Letta server
2. Create agents with karla tools
3. Send messages and execute tool calls client-side
4. Send results back to Letta and continue the loop

Based on the Lares pattern for client-side tool execution.

Run with: pytest tests/test_letta_e2e.py -v -s
"""

import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from letta_client import Letta

from karla import ToolExecutor, create_default_registry, load_config, create_client
from karla.letta import register_tools_with_letta


@dataclass
class PendingToolCall:
    """A tool call that needs client-side execution."""
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class MessageResponse:
    """Response from sending a message."""
    text: str | None
    pending_tool_calls: list[PendingToolCall]


def send_message(client: Letta, agent_id: str, message: str) -> MessageResponse:
    """Send a message and parse response for tool calls."""
    response = client.agents.messages.create(
        agent_id=agent_id,
        messages=[{"role": "user", "content": message}],
    )

    text_response: str | None = None
    pending_tools: list[PendingToolCall] = []

    for msg in response.messages:
        msg_type = type(msg).__name__

        # Check for approval requests (tool calls needing execution)
        if msg_type == "ApprovalRequestMessage" and hasattr(msg, "tool_call"):
            tool_call = msg.tool_call
            arguments_str = getattr(tool_call, "arguments", "") or ""
            tool_call_id = getattr(tool_call, "tool_call_id", "") or ""
            tool_name = getattr(tool_call, "name", "") or ""

            try:
                args = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                args = {"raw": arguments_str}

            if tool_call_id and tool_name:
                pending_tools.append(PendingToolCall(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    arguments=args,
                ))

        # Extract text response
        elif hasattr(msg, "content") and msg.content:
            if hasattr(msg, "role") and msg.role == "assistant":
                text_response = str(msg.content)

    return MessageResponse(text=text_response, pending_tool_calls=pending_tools)


def send_tool_result(
    client: Letta,
    agent_id: str,
    tool_call_id: str,
    result: str,
    status: str = "success",
) -> MessageResponse:
    """Send tool execution result back to Letta."""
    response = client.agents.messages.create(
        agent_id=agent_id,
        messages=[{
            "type": "approval",
            "approvals": [{
                "type": "tool",
                "tool_call_id": tool_call_id,
                "tool_return": result,
                "status": status,
            }]
        }],
    )

    text_response: str | None = None
    pending_tools: list[PendingToolCall] = []

    for msg in response.messages:
        msg_type = type(msg).__name__

        if msg_type == "ApprovalRequestMessage" and hasattr(msg, "tool_call"):
            tool_call = msg.tool_call
            arguments_str = getattr(tool_call, "arguments", "") or ""
            tool_call_id = getattr(tool_call, "tool_call_id", "") or ""
            tool_name = getattr(tool_call, "name", "") or ""

            try:
                args = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                args = {"raw": arguments_str}

            if tool_call_id and tool_name:
                pending_tools.append(PendingToolCall(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    arguments=args,
                ))

        elif hasattr(msg, "content") and msg.content:
            if hasattr(msg, "role") and msg.role == "assistant":
                text_response = str(msg.content)

    return MessageResponse(text=text_response, pending_tool_calls=pending_tools)


def letta_server_available() -> bool:
    """Check if Letta server is running."""
    try:
        client = Letta(base_url="http://localhost:8283", timeout=5)
        list(client.tools.list(limit=1))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not letta_server_available(),
    reason="Letta server not available at localhost:8283"
)


@pytest.fixture(scope="module")
def karla_config():
    """Load karla config."""
    config_path = Path(__file__).parent.parent / "karla.yaml"
    if not config_path.exists():
        pytest.skip("karla.yaml not found")
    return load_config(config_path)


@pytest.fixture(scope="module")
def letta_client(karla_config):
    """Create Letta client."""
    return create_client(karla_config)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "hello.txt").write_text("Hello from E2E test!")
        (Path(tmpdir) / "data.json").write_text('{"key": "value", "number": 42}')
        yield tmpdir


@pytest.fixture
def tool_registry(temp_workspace):
    """Create tool registry."""
    return create_default_registry(temp_workspace)


@pytest.fixture
def tool_executor(tool_registry, temp_workspace):
    """Create tool executor."""
    return ToolExecutor(tool_registry, temp_workspace)


class TestLettaConnection:
    """Test basic Letta connectivity."""

    def test_server_responds(self, letta_client):
        """Verify Letta server is responding."""
        tools = list(letta_client.tools.list(limit=1))
        assert tools is not None


class TestToolRegistration:
    """Test registering karla tools with Letta."""

    def test_register_tools(self, letta_client, karla_config, tool_registry):
        """Test tools can be registered."""
        agent = letta_client.agents.create(
            name=f"karla-reg-{uuid.uuid4().hex[:8]}",
            system="Test agent",
            llm_config=karla_config.llm.to_dict(),
            embedding="letta/letta-free",
            include_base_tools=False,
        )

        try:
            registered = register_tools_with_letta(letta_client, agent.id, tool_registry)
            assert "Read" in registered
            assert "Write" in registered
            assert "Bash" in registered
        finally:
            letta_client.agents.delete(agent.id)


class TestToolExecutionLoop:
    """Test the full tool execution loop."""

    @pytest.fixture
    def agent(self, letta_client, karla_config, tool_registry):
        """Create agent with tools."""
        agent = letta_client.agents.create(
            name=f"karla-e2e-{uuid.uuid4().hex[:8]}",
            system="""You are a coding assistant with file tools.
When asked to read a file, use the Read tool.
When asked to write a file, use the Write tool.
When asked to run a command, use the Bash tool.
Always use tools to complete tasks.""",
            llm_config=karla_config.llm.to_dict(),
            embedding="letta/letta-free",
            include_base_tools=False,
        )

        register_tools_with_letta(letta_client, agent.id, tool_registry)

        yield agent

        letta_client.agents.delete(agent.id)

    def _run_with_tools(
        self,
        client: Letta,
        agent_id: str,
        message: str,
        executor: ToolExecutor,
        max_iterations: int = 10,
    ) -> tuple[list[dict], MessageResponse]:
        """Run message through full tool execution loop."""
        import asyncio

        all_results = []
        response = send_message(client, agent_id, message)

        iterations = 0
        while response.pending_tool_calls and iterations < max_iterations:
            iterations += 1

            for tool_call in response.pending_tool_calls:
                # Execute tool locally
                result = asyncio.run(executor.execute(
                    tool_call.name,
                    tool_call.arguments
                ))

                all_results.append({
                    "tool": tool_call.name,
                    "args": tool_call.arguments,
                    "output": result.output,
                    "is_error": result.is_error,
                })

                # Send result back
                response = send_tool_result(
                    client,
                    agent_id,
                    tool_call.tool_call_id,
                    result.output,
                    "error" if result.is_error else "success",
                )

                # Break to check new response's pending_tool_calls
                break

        return all_results, response

    def test_read_file(self, letta_client, agent, tool_executor, temp_workspace):
        """Test reading a file through the loop."""
        results, response = self._run_with_tools(
            letta_client,
            agent.id,
            f"Read {temp_workspace}/hello.txt",
            tool_executor,
        )

        # Should have Read tool call
        read_results = [r for r in results if r["tool"] == "Read"]
        assert len(read_results) > 0
        assert "Hello from E2E test!" in read_results[0]["output"]

    def test_write_file(self, letta_client, agent, tool_executor, temp_workspace):
        """Test writing a file through the loop."""
        new_file = Path(temp_workspace) / "created.txt"

        results, response = self._run_with_tools(
            letta_client,
            agent.id,
            f"Create a file at {new_file} with content 'Created by Karla E2E'",
            tool_executor,
        )

        # Should have Write tool call
        write_results = [r for r in results if r["tool"] == "Write"]
        assert len(write_results) > 0

        # File should exist
        assert new_file.exists()
        assert "Karla" in new_file.read_text() or "Created" in new_file.read_text()

    def test_bash_command(self, letta_client, agent, tool_executor, temp_workspace):
        """Test running bash command through the loop."""
        results, response = self._run_with_tools(
            letta_client,
            agent.id,
            "Run 'echo KARLA_E2E_SUCCESS' using the Bash tool",
            tool_executor,
        )

        # Should have Bash tool call
        bash_results = [r for r in results if r["tool"] == "Bash"]
        assert len(bash_results) > 0
        assert "KARLA_E2E_SUCCESS" in bash_results[0]["output"]

    def test_multi_tool_workflow(self, letta_client, agent, tool_executor, temp_workspace):
        """Test workflow requiring multiple tool calls."""
        # Create initial file
        source = Path(temp_workspace) / "source.txt"
        source.write_text("Original content for copy test")

        results, response = self._run_with_tools(
            letta_client,
            agent.id,
            f"Read {source} and create a new file {temp_workspace}/copy.txt with the same content",
            tool_executor,
            max_iterations=15,
        )

        # Should have both Read and Write
        tools_used = [r["tool"] for r in results]
        assert "Read" in tools_used
        assert "Write" in tools_used


class TestErrorHandling:
    """Test error handling."""

    @pytest.fixture
    def agent(self, letta_client, karla_config, tool_registry):
        """Create agent for error tests."""
        agent = letta_client.agents.create(
            name=f"karla-err-{uuid.uuid4().hex[:8]}",
            system="You are a coding assistant. Handle errors gracefully.",
            llm_config=karla_config.llm.to_dict(),
            embedding="letta/letta-free",
            include_base_tools=False,
        )

        register_tools_with_letta(letta_client, agent.id, tool_registry)

        yield agent

        letta_client.agents.delete(agent.id)

    def test_read_nonexistent_file(self, letta_client, agent, tool_executor, temp_workspace):
        """Test error when reading nonexistent file."""
        import asyncio

        response = send_message(
            letta_client,
            agent.id,
            f"Read {temp_workspace}/nonexistent.txt"
        )

        for tc in response.pending_tool_calls:
            if tc.name == "Read":
                result = asyncio.run(tool_executor.execute(tc.name, tc.arguments))
                assert result.is_error
                assert "does not exist" in result.output.lower()
