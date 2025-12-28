"""Main agent loop for Karla with client-side tool execution.

This module implements the core message loop that:
1. Sends messages to the Letta agent
2. Receives responses (including tool calls)
3. Executes tools client-side
4. Sends results back via the approval flow
5. Continues until no more tool calls or the agent completes
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from letta_client import Letta

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
    """Parse a Letta message response for text and tool calls.

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
    client: Letta,
    agent_id: str,
    tool_call_id: str,
    result: str,
    status: str = "success",
):
    """Send tool execution result back to Letta via approval flow.

    Args:
        client: Letta client
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


async def _send_with_retry(
    client: Letta,
    agent_id: str,
    messages: list,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
):
    """Send a message with retry logic for transient errors.

    Args:
        client: Letta client
        agent_id: Agent ID
        messages: Messages to send
        max_retries: Maximum number of retries
        retry_delay: Delay between retries in seconds

    Returns:
        Response from the API

    Raises:
        Exception: If all retries fail
    """
    import asyncio

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return client.agents.messages.create(
                agent_id=agent_id,
                messages=messages,
            )
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    "Request failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1, max_retries + 1, e, retry_delay
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Request failed after %d attempts: %s", max_retries + 1, e)

    raise last_error


async def run_agent_loop(
    client: Letta,
    agent_id: str,
    executor: ToolExecutor,
    message: str,
    max_iterations: int = 50,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_tool_start: Optional[Callable[[str, dict], None]] = None,
    on_tool_end: Optional[Callable[[str, str, bool], None]] = None,
    on_text: Optional[Callable[[str], None]] = None,
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
        client: Letta client
        agent_id: Agent ID
        executor: Tool executor for client-side execution
        message: Initial user message
        max_iterations: Maximum tool execution iterations
        max_retries: Maximum retries for API errors
        on_tool_start: Callback when tool execution starts
        on_tool_end: Callback when tool execution ends
        on_text: Callback when text response received
        hooks_manager: Optional hooks manager for event callbacks

    Returns:
        AgentResponse with final text and all tool results
    """
    all_results: list[ToolResult] = []
    final_text: Optional[str] = None
    iterations = 0

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

    # Send initial message with retry
    response = await _send_with_retry(
        client, agent_id,
        [{"role": "user", "content": message}],
        max_retries=max_retries,
    )

    text, pending_tools = parse_message_response(response)
    if text:
        final_text = text
        if on_text:
            on_text(text)

    # Process tool calls in a loop
    while pending_tools and iterations < max_iterations:
        iterations += 1

        for tool_call in pending_tools:
            logger.debug(
                "Executing tool: %s (id=%s)",
                tool_call.name,
                tool_call.tool_call_id
            )

            if on_tool_start:
                on_tool_start(tool_call.name, tool_call.arguments)

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
                on_tool_end(tool_call.name, result.output, result.is_error)

            # Run on_tool_end hooks
            if hooks_manager:
                await hooks_manager.run_hooks("on_tool_end", {
                    "agent_id": agent_id,
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.tool_call_id,
                    "output": result.output,
                    "is_error": result.is_error,
                })

            # Send result back with retry
            response = await _send_with_retry(
                client,
                agent_id,
                [{
                    "type": "approval",
                    "approvals": [{
                        "type": "tool",
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_return": result.output,
                        "status": "error" if result.is_error else "success",
                    }]
                }],
                max_retries=max_retries,
            )

            # Parse new response
            text, pending_tools = parse_message_response(response)
            if text:
                final_text = text
                if on_text:
                    on_text(text)

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
