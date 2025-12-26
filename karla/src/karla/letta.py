"""Letta integration layer for tool registration and agent interaction."""

import logging
from typing import Any

from letta_client import Letta

from karla.executor import ToolExecutor
from karla.registry import ToolRegistry

logger = logging.getLogger(__name__)


def register_tools_with_letta(
    client: Letta,
    agent_id: str,
    registry: ToolRegistry,
    requires_approval: bool = True,
) -> list[str]:
    """Register tools from a registry with a Letta agent.

    Tools are registered with requires_approval=True because they execute
    client-side (the Python stubs just raise Exception). The approval flow
    is how Letta hands control back to the client for execution.

    For HOTL (humans out of the loop), the client auto-approves and executes
    without user confirmation - that's handled in the client loop, not here.

    Args:
        client: Letta client instance
        agent_id: ID of the agent to attach tools to
        registry: Tool registry containing tools to register
        requires_approval: Must be True for client-side tools (default).

    Returns:
        List of registered tool names
    """
    logger.info("Registering %d tools with agent %s", len(registry), agent_id)

    registered: list[str] = []
    tool_ids: list[str] = []

    # Get both source code stubs and OpenAI-format schemas
    sources = registry.to_letta_sources()
    schemas = {tool.name: tool.definition().to_openai_schema(strict=True) for tool in registry}

    for name, source_code in sources.items():
        try:
            # Build json_schema in Letta's expected format
            # This is what the LLM actually sees - NOT derived from parsing Python
            openai_schema = schemas.get(name, {})
            func_schema = openai_schema.get("function", {})

            json_schema = {
                "name": name,
                "description": func_schema.get("description", ""),
                "parameters": func_schema.get("parameters", {}),
            }

            tool = client.tools.upsert(
                source_code=source_code,
                json_schema=json_schema,  # Explicit schema for LLM
                default_requires_approval=requires_approval,
            )
            logger.info("Registered tool: %s (id=%s)", name, tool.id)
            registered.append(name)
            tool_ids.append(tool.id)
        except Exception as e:
            logger.error("Failed to register tool %s: %s", name, e)

    # Attach tools to agent
    for tool_id in tool_ids:
        try:
            client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
            logger.debug("Attached tool %s to agent", tool_id)
        except Exception as e:
            # May already be attached
            logger.debug("Tool attach failed (may already be attached): %s", e)

    return registered


class LettaAgent:
    """Wrapper around a Letta agent with client-side tool execution."""

    def __init__(
        self,
        client: Letta,
        agent_id: str,
        executor: ToolExecutor,
    ) -> None:
        self.client = client
        self.agent_id = agent_id
        self.executor = executor

    async def send_message(
        self,
        message: str,
        stream: bool = True,
    ):
        """Send a message to the agent and handle tool calls.

        This is an async generator that yields events as they come in:
        - TextDelta: streaming text from the agent
        - ToolCallStart: tool call initiated
        - ToolCallEnd: tool call completed with result
        - Complete: agent finished responding

        Args:
            message: User message to send
            stream: Whether to stream the response

        Yields:
            Event dictionaries with type and data
        """
        # Send initial message
        response_stream = self.client.agents.messages.stream(
            self.agent_id,
            messages=[{"role": "user", "content": message}],
            stream_tokens=stream,
        )

        pending_approvals = []

        async for chunk in self._iterate_stream(response_stream):
            chunk_type = chunk.get("message_type")

            if chunk_type == "text_delta":
                yield {"type": "text_delta", "delta": chunk.get("delta", "")}

            elif chunk_type == "tool_call":
                tool_name = chunk.get("tool_name", "")
                tool_args = chunk.get("tool_arguments", {})
                tool_call_id = chunk.get("tool_call_id", "")

                yield {
                    "type": "tool_call_start",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_call_id": tool_call_id,
                }

                # Execute tool locally
                result = await self.executor.execute(tool_name, tool_args)

                yield {
                    "type": "tool_call_end",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "result": result.output,
                    "is_error": result.is_error,
                }

                # Queue approval response
                pending_approvals.append(
                    {
                        "type": "tool",
                        "tool_call_id": tool_call_id,
                        "tool_return": result.output,
                        "status": "error" if result.is_error else "success",
                    }
                )

            elif chunk_type == "usage":
                yield {
                    "type": "usage",
                    "input_tokens": chunk.get("prompt_tokens", 0),
                    "output_tokens": chunk.get("completion_tokens", 0),
                }

            elif chunk_type == "done" or chunk_type == "stop":
                stop_reason = chunk.get("stop_reason", "end_turn")

                # If there are pending approvals, send them back
                if pending_approvals:
                    # Continue the conversation with tool results
                    response_stream = self.client.agents.messages.stream(
                        self.agent_id,
                        messages=pending_approvals,
                        stream_tokens=stream,
                    )
                    pending_approvals = []

                    # Recursively process the continuation
                    async for event in self._iterate_stream(response_stream):
                        # Re-yield events from continuation
                        # (This is simplified - in practice you'd handle this more carefully)
                        pass

                yield {"type": "complete", "stop_reason": stop_reason}
                break

    async def _iterate_stream(self, stream):
        """Iterate over a Letta stream, handling sync iteration in async context."""
        # The Letta SDK returns a sync iterator, wrap it for async
        for chunk in stream:
            # Convert to dict if needed
            if hasattr(chunk, "model_dump"):
                yield chunk.model_dump()
            elif hasattr(chunk, "__dict__"):
                yield {"message_type": getattr(chunk, "message_type", "unknown"), **chunk.__dict__}
            else:
                yield chunk
