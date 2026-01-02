"""Main agent loop for Karla with client-side tool execution.

This module implements the core message loop that:
1. Sends messages to the Crow agent
2. Receives responses (including tool calls)
3. Executes tools client-side
4. Sends results back via the approval flow
5. Continues until no more tool calls or the agent completes
"""

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Union

from crow_client import Crow

from karla.executor import ToolExecutor
from karla.hooks import HooksManager, run_hooks
from karla.tool import ToolResult as ExecutorToolResult

logger = logging.getLogger(__name__)


class OutputFormat(Enum):
    """Output format for agent responses."""
    TEXT = "text"
    JSON = "json"
    STREAM_JSON = "stream-json"


@dataclass
class PendingToolCall:
    """A tool call that needs client-side execution."""
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_call_id: str
    name: str
    output: str
    is_error: bool


@dataclass
class AgentResponse:
    """Complete response from the agent loop."""
    text: Optional[str]
    tool_results: list[ToolResult] = field(default_factory=list)
    iterations: int = 0


def parse_message_response(response) -> tuple[Optional[str], list[PendingToolCall]]:
    """Parse a Crow message response for text and tool calls.

    Args:
        response: Response from client.agents.messages.create()

    Returns:
        Tuple of (text_response, pending_tool_calls)
    """
    text_response: Optional[str] = None
    pending_tools: list[PendingToolCall] = []

    for msg in response.messages:
        msg_type = type(msg).__name__
        logger.debug("Message type: %s", msg_type)

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

        # Check AssistantMessage type first (most common response type)
        elif msg_type == "AssistantMessage" and hasattr(msg, "content") and msg.content:
            logger.debug("AssistantMessage: %s", msg.content[:100] if len(msg.content) > 100 else msg.content)
            text_response = str(msg.content)

        # Also check for messages with role="assistant"
        elif hasattr(msg, "content") and msg.content:
            role = getattr(msg, "role", None)
            if role == "assistant":
                text_response = str(msg.content)

    return text_response, pending_tools


def send_approval(
    client: Crow,
    agent_id: str,
    tool_call_id: str,
    result: str,
    status: str = "success",
):
    """Send tool execution result back to Crow via approval flow.

    Args:
        client: Crow client
        agent_id: Agent ID
        tool_call_id: ID of the tool call being responded to
        result: Tool execution output
        status: "success" or "error"

    Returns:
        Response from the agent
    """
    return client.agents.messages.create(
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


DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds

# Callback types that can be sync or async
ToolStartCallback = Callable[[str, dict], Union[None, Awaitable[None]]]
ToolEndCallback = Callable[[str, str, bool], Union[None, Awaitable[None]]]
TextCallback = Callable[[str], Union[None, Awaitable[None]]]
ReasoningCallback = Callable[[str], Union[None, Awaitable[None]]]  # For agent's internal thinking
# For internal/server-side tools (memory operations) - (name, args)
InternalToolCallback = Callable[[str, dict], Union[None, Awaitable[None]]]


async def _maybe_await(result: Union[None, Awaitable[None]]) -> None:
    """Await the result if it's a coroutine, otherwise do nothing."""
    if result is not None and inspect.iscoroutine(result):
        await result


async def _stream_message(
    client: Crow,
    agent_id: str,
    messages: list,
    on_text: Optional[TextCallback] = None,
    on_tool_start: Optional[ToolStartCallback] = None,
    on_reasoning: Optional[ReasoningCallback] = None,
    on_internal_tool: Optional[InternalToolCallback] = None,
) -> tuple[Optional[str], list[PendingToolCall]]:
    """Stream a message and return accumulated text and any pending tool calls.

    Args:
        client: Crow client
        agent_id: Agent ID
        messages: Messages to send
        on_text: Callback for text chunks (called for each token)
        on_tool_start: Callback when tool call detected (name, partial args)
        on_reasoning: Callback for reasoning/thinking chunks (agent's internal monologue)
        on_internal_tool: Callback for internal/server-side tool calls (memory operations)

    Returns:
        Tuple of (accumulated_text, pending_tool_calls)
    """
    accumulated_text = ""
    pending_tools: list[PendingToolCall] = []

    # Track tool calls being built up from deltas
    tool_calls_in_progress: dict[str, dict] = {}  # tool_call_id -> {name, arguments}

    # Use streaming API
    stream = client.agents.messages.stream(
        agent_id=agent_id,
        messages=messages,
        stream_tokens=True,
    )

    for chunk in stream:
        chunk_type = type(chunk).__name__

        # Handle reasoning/thinking tokens (agent's internal monologue)
        if chunk_type == "ReasoningMessage" and hasattr(chunk, "reasoning") and chunk.reasoning:
            reasoning_token = str(chunk.reasoning)
            if on_reasoning:
                await _maybe_await(on_reasoning(reasoning_token))

        # Handle text tokens (assistant's response to user)
        elif chunk_type == "AssistantMessage" and hasattr(chunk, "content") and chunk.content:
            token = str(chunk.content)
            accumulated_text += token
            if on_text:
                await _maybe_await(on_text(token))

        # Handle internal/server-side tool calls (memory operations)
        # These are executed by Crow server, not client-side
        elif chunk_type == "ToolCallMessage" and hasattr(chunk, "tool_call"):
            tc = chunk.tool_call
            tc_name = getattr(tc, "name", None)
            tc_args_str = getattr(tc, "arguments", None)

            if tc_name and on_internal_tool:
                # Parse arguments if present
                try:
                    args = json.loads(tc_args_str) if tc_args_str else {}
                except json.JSONDecodeError:
                    args = {"raw": tc_args_str} if tc_args_str else {}
                await _maybe_await(on_internal_tool(tc_name, args))

        # Handle tool call deltas - accumulate them (client-side tools needing approval)
        elif chunk_type == "ApprovalRequestMessage" and hasattr(chunk, "tool_call"):
            tc = chunk.tool_call
            tc_id = getattr(tc, "tool_call_id", "") or ""
            tc_name = getattr(tc, "name", None)
            tc_args = getattr(tc, "arguments", None)

            if not tc_id:
                continue

            # Initialize or update the in-progress tool call
            if tc_id not in tool_calls_in_progress:
                tool_calls_in_progress[tc_id] = {"name": "", "arguments": ""}

            if tc_name:
                tool_calls_in_progress[tc_id]["name"] = tc_name
                # Notify that a tool call started
                if on_tool_start:
                    await _maybe_await(on_tool_start(tc_name, {}))

            if tc_args:
                tool_calls_in_progress[tc_id]["arguments"] += tc_args

        # Stop/usage messages are just logged
        elif chunk_type in ("CrowStopReason", "CrowUsageStatistics"):
            logger.debug("Stream end: %s", chunk_type)

    # Convert accumulated tool calls to PendingToolCall objects
    for tc_id, tc_data in tool_calls_in_progress.items():
        if tc_data["name"]:
            try:
                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool args: %s", tc_data["arguments"][:100])
                args = {}

            pending_tools.append(PendingToolCall(
                tool_call_id=tc_id,
                name=tc_data["name"],
                arguments=args,
            ))

    return accumulated_text if accumulated_text else None, pending_tools


async def _send_approval(
    client: Crow,
    agent_id: str,
    tool_call_id: str,
    result: str,
    is_error: bool,
    on_text: Optional[TextCallback] = None,
    on_reasoning: Optional[ReasoningCallback] = None,
    on_internal_tool: Optional[InternalToolCallback] = None,
) -> tuple[Optional[str], list[PendingToolCall]]:
    """Send tool result and stream the response.

    Args:
        client: Crow client
        agent_id: Agent ID
        tool_call_id: ID of the tool call being responded to
        result: Tool execution output
        is_error: Whether the tool execution failed
        on_reasoning: Callback for reasoning/thinking chunks
        on_text: Callback for text chunks
        on_internal_tool: Callback for internal/server-side tool calls

    Returns:
        Tuple of (text_response, pending_tool_calls)
    """
    return await _stream_message(
        client,
        agent_id,
        [{
            "type": "approval",
            "approvals": [{
                "type": "tool",
                "tool_call_id": tool_call_id,
                "tool_return": result,
                "status": "error" if is_error else "success",
            }]
        }],
        on_text=on_text,
        on_reasoning=on_reasoning,
        on_internal_tool=on_internal_tool,
    )


async def run_agent_loop(
    client: Crow,
    agent_id: str,
    executor: ToolExecutor,
    message: str,
    max_iterations: int = 50,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_tool_start: Optional[ToolStartCallback] = None,
    on_tool_end: Optional[ToolEndCallback] = None,
    on_text: Optional[TextCallback] = None,
    on_reasoning: Optional[ReasoningCallback] = None,
    on_internal_tool: Optional[InternalToolCallback] = None,
    hooks_manager: Optional[HooksManager] = None,
) -> AgentResponse:
    """Run the main agent loop with client-side tool execution.

    This implements the core loop:
    1. Send user message
    2. Check for tool calls in response
    3. Execute tools client-side
    4. Send results back via approval
    5. Repeat until no more tool calls

    Includes retry logic for transient API errors.

    Args:
        client: Crow client
        agent_id: Agent ID
        executor: Tool executor for client-side execution
        message: Initial user message
        max_iterations: Maximum tool execution iterations
        max_retries: Maximum retries for API errors
        on_tool_start: Callback when tool execution starts
        on_tool_end: Callback when tool execution ends
        on_text: Callback when text response received
        on_reasoning: Callback for reasoning/thinking chunks (agent's internal monologue)
        on_internal_tool: Callback for internal/server-side tool calls (memory operations)
        hooks_manager: Optional hooks manager for event callbacks

    Returns:
        AgentResponse with final text and all tool results
    """
    all_results: list[ToolResult] = []
    final_text: Optional[str] = None
    iterations = 0

    # Reset cancellation state at start of new prompt
    executor.reset()

    # Run on_loop_start hooks
    if hooks_manager:
        await hooks_manager.run_hooks("on_loop_start", {
            "agent_id": agent_id,
            "message": message,
        })

    # Run on_prompt_submit hooks
    if hooks_manager:
        hook_results = await hooks_manager.run_hooks("on_prompt_submit", {
            "agent_id": agent_id,
            "message": message,
        })
        # Check if any hook blocked the prompt
        for hr in hook_results:
            if hr.block:
                return AgentResponse(
                    text=hr.error or "Prompt blocked by hook",
                    tool_results=[],
                    iterations=0,
                )
            # Inject hook messages if any
            if hr.inject_message:
                message = f"{message}\n\n<user-prompt-submit-hook>\n{hr.inject_message}\n</user-prompt-submit-hook>"

    # Send initial message with streaming
    text, pending_tools = await _stream_message(
        client, agent_id,
        [{"role": "user", "content": message}],
        on_text=on_text,
        on_reasoning=on_reasoning,
        on_internal_tool=on_internal_tool,
    )
    if text:
        final_text = text

    # Process tool calls in a loop
    while pending_tools and iterations < max_iterations:
        # Check for cancellation
        if executor._cancelled:
            logger.info("Agent loop cancelled at iteration %d", iterations)
            return AgentResponse(
                text="Cancelled",
                tool_results=all_results,
                iterations=iterations,
            )

        iterations += 1

        for tool_call in pending_tools:
            logger.debug(
                "Executing tool: %s (id=%s)",
                tool_call.name,
                tool_call.tool_call_id
            )

            if on_tool_start:
                await _maybe_await(on_tool_start(tool_call.name, tool_call.arguments))

            # Run on_tool_start hooks
            if hooks_manager:
                hook_results = await hooks_manager.run_hooks("on_tool_start", {
                    "agent_id": agent_id,
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.tool_call_id,
                    "arguments": tool_call.arguments,
                })
                # Check if any hook blocked the tool
                for hr in hook_results:
                    if hr.block:
                        result = ExecutorToolResult.error(hr.error or "Tool blocked by hook")
                        break
                else:
                    # No hook blocked, execute the tool
                    result = await executor.execute(tool_call.name, tool_call.arguments)
            else:
                # Execute tool locally
                result = await executor.execute(tool_call.name, tool_call.arguments)

            all_results.append(ToolResult(
                tool_call_id=tool_call.tool_call_id,
                name=tool_call.name,
                output=result.output,
                is_error=result.is_error,
            ))

            if on_tool_end:
                await _maybe_await(on_tool_end(tool_call.name, result.output, result.is_error))

            # Run on_tool_end hooks
            if hooks_manager:
                await hooks_manager.run_hooks("on_tool_end", {
                    "agent_id": agent_id,
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.tool_call_id,
                    "output": result.output,
                    "is_error": result.is_error,
                })

            # Check for cancellation before sending approval
            if executor._cancelled:
                logger.info("Agent loop cancelled after tool %s", tool_call.name)
                return AgentResponse(
                    text="Cancelled",
                    tool_results=all_results,
                    iterations=iterations,
                )

            # Send result back with streaming
            text, pending_tools = await _send_approval(
                client,
                agent_id,
                tool_call.tool_call_id,
                result.output,
                result.is_error,
                on_text=on_text,
                on_reasoning=on_reasoning,
                on_internal_tool=on_internal_tool,
            )
            if text:
                final_text = text

            # Break to restart loop with new pending tools
            break

    if iterations >= max_iterations:
        logger.warning("Hit max iterations (%d) in agent loop", max_iterations)

    # Run on_message hooks if there's a text response
    if hooks_manager and final_text:
        await hooks_manager.run_hooks("on_message", {
            "agent_id": agent_id,
            "text": final_text,
            "iterations": iterations,
        })

    # Run on_loop_end hooks
    if hooks_manager:
        await hooks_manager.run_hooks("on_loop_end", {
            "agent_id": agent_id,
            "text": final_text,
            "iterations": iterations,
            "tool_count": len(all_results),
        })

    return AgentResponse(
        text=final_text,
        tool_results=all_results,
        iterations=iterations,
    )


def format_response(response: AgentResponse, format: OutputFormat) -> str:
    """Format agent response for output.

    Args:
        response: AgentResponse from run_agent_loop
        format: Output format (text, json, stream-json)

    Returns:
        Formatted string
    """
    if format == OutputFormat.TEXT:
        return response.text or ""

    elif format == OutputFormat.JSON:
        return json.dumps({
            "text": response.text,
            "tool_results": [
                {
                    "name": r.name,
                    "output": r.output,
                    "is_error": r.is_error,
                }
                for r in response.tool_results
            ],
            "iterations": response.iterations,
        }, indent=2)

    else:  # stream-json - in practice would be streamed
        return json.dumps({
            "text": response.text,
            "iterations": response.iterations,
        })
