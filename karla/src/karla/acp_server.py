"""ACP (Agent Communication Protocol) server wrapper for Karla.

This wraps the Karla/Letta agent as an ACP-compliant server that can be
consumed by ACP clients.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

# Add python-sdk to path (local development)
_python_sdk_path = Path(__file__).parent.parent.parent.parent / "python-sdk" / "src"
if _python_sdk_path.exists() and str(_python_sdk_path) not in sys.path:
    sys.path.insert(0, str(_python_sdk_path))

from acp import (
    PROTOCOL_VERSION,
    Agent,
    InitializeResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    start_tool_call,
    text_block,
    update_agent_message,
    update_agent_thought,
    update_tool_call,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
    ToolCallLocation,
)

from karla.agent import create_karla_agent, get_or_create_agent
from karla.agent_loop import run_agent_loop
from karla.commands.context import CommandContext
from karla.commands.dispatcher import dispatch_command
from karla.config import KarlaConfig, create_client, load_config
from karla.context import AgentContext, set_context, clear_context
from karla.executor import ToolExecutor
from karla.letta import register_tools_with_letta
from karla.memory import update_project_block
from karla.settings import SettingsManager
from karla.tools import create_default_registry

logger = logging.getLogger(__name__)


# Map Karla tool names to ACP ToolKind
TOOL_KIND_MAP = {
    "Read": "read",
    "Glob": "search",
    "Grep": "search",
    "Write": "edit",
    "Edit": "edit",
    "Bash": "execute",
    "BashOutput": "execute",
    "KillBash": "execute",
    "WebSearch": "fetch",
    "WebFetch": "fetch",
    "Task": "other",
    "TodoWrite": "other",
    "Skill": "other",
    "AskUserQuestion": "other",
    "EnterPlanMode": "think",
    "ExitPlanMode": "think",
}


def get_tool_info(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Generate rich tool call info for ACP (title, content, locations)."""
    kind = TOOL_KIND_MAP.get(name, "other")
    locations = []
    content = []

    if name == "Read":
        path = args.get("file_path", "")
        limit_str = ""
        if args.get("limit"):
            offset = args.get("offset", 0)
            limit_str = f" ({offset + 1} - {offset + args['limit']})"
        elif args.get("offset"):
            limit_str = f" (from line {args['offset'] + 1})"
        title = f"Read {path}{limit_str}" if path else "Read File"
        if path:
            locations = [{"path": path, "line": args.get("offset", 0)}]

    elif name == "Write":
        path = args.get("file_path", "")
        title = f"Write {path}" if path else "Write"
        if path:
            locations = [{"path": path}]
            # Diff showing new file creation
            content = [{
                "type": "diff",
                "path": path,
                "oldText": None,
                "newText": args.get("content", ""),
            }]

    elif name == "Edit":
        path = args.get("file_path", "")
        title = f"Edit `{path}`" if path else "Edit"
        if path:
            locations = [{"path": path}]
            # Show the diff (old_string -> new_string)
            old_str = args.get("old_string", "")
            new_str = args.get("new_string", "")
            content = [{
                "type": "diff",
                "path": path,
                "oldText": old_str,
                "newText": new_str,
            }]

    elif name == "Bash":
        cmd = args.get("command", "")
        title = f"`{cmd}`" if cmd else "Terminal"
        if args.get("description"):
            content = [{"type": "content", "content": {"type": "text", "text": args["description"]}}]

    elif name == "BashOutput":
        title = "Tail Logs"

    elif name == "KillBash":
        title = "Kill Process"

    elif name == "Glob":
        parts = ["Find"]
        if args.get("path"):
            parts.append(f"`{args['path']}`")
        if args.get("pattern"):
            parts.append(f"`{args['pattern']}`")
        title = " ".join(parts)
        if args.get("path"):
            locations = [{"path": args["path"]}]

    elif name == "Grep":
        parts = ["grep"]
        if args.get("-i"):
            parts.append("-i")
        if args.get("-n"):
            parts.append("-n")
        if args.get("-A") is not None:
            parts.append(f"-A {args['-A']}")
        if args.get("-B") is not None:
            parts.append(f"-B {args['-B']}")
        if args.get("-C") is not None:
            parts.append(f"-C {args['-C']}")
        if args.get("pattern"):
            parts.append(f'"{args["pattern"]}"')
        if args.get("path"):
            parts.append(args["path"])
        title = " ".join(parts)

    elif name == "WebSearch":
        query = args.get("query", "")
        title = f'"{query}"' if query else "Web Search"

    elif name == "WebFetch":
        url = args.get("url", "")
        title = f"Fetch {url}" if url else "Fetch"
        if args.get("prompt"):
            content = [{"type": "content", "content": {"type": "text", "text": args["prompt"]}}]

    elif name == "Task":
        title = args.get("description", "Task")
        if args.get("prompt"):
            content = [{"type": "content", "content": {"type": "text", "text": args["prompt"]}}]

    elif name == "TodoWrite":
        todos = args.get("todos", [])
        if todos:
            items = ", ".join(t.get("content", "") for t in todos[:3])
            title = f"Update TODOs: {items}"
        else:
            title = "Update TODOs"

    elif name in ("EnterPlanMode", "ExitPlanMode"):
        title = "Ready to code?" if name == "ExitPlanMode" else "Plan Mode"

    else:
        title = name

    return {
        "title": title,
        "kind": kind,
        "content": content,
        "locations": locations,
    }


def get_tool_result_content(name: str, output: str, is_error: bool) -> list[dict]:
    """Generate content for tool result update."""
    if not output:
        return []

    # For Read, show the file content
    if name == "Read":
        return [{"type": "content", "content": {"type": "text", "text": f"```\n{output}\n```"}}]

    # For Bash, show terminal output
    if name in ("Bash", "BashOutput"):
        return [{"type": "content", "content": {"type": "text", "text": f"```\n{output}\n```"}}]

    # For errors, wrap in code block
    if is_error:
        return [{"type": "content", "content": {"type": "text", "text": f"```\n{output}\n```"}}]

    # For Write/Edit success, don't return content (diff was shown at start)
    if name in ("Write", "Edit") and not is_error:
        return []

    # Default: return raw output
    return [{"type": "content", "content": {"type": "text", "text": output}}]


class KarlaAgent(Agent):
    """ACP wrapper for Karla agent."""

    _conn: Client
    _config: KarlaConfig
    _sessions: dict[str, dict[str, Any]]  # session_id -> session state

    def __init__(self, config: KarlaConfig | None = None) -> None:
        self._config = config or load_config()
        self._sessions = {}

    def on_connect(self, conn: Client) -> None:
        """Called when a client connects."""
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Handle initialize request from client."""
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                load_session=True,
                prompt_capabilities=None,  # text only for now
            ),
            agent_info=Implementation(
                name="karla",
                title="Karla Coding Agent",
                version="0.1.0",
            ),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Create a new session (creates a new Letta agent)."""
        session_id = uuid4().hex
        client = create_client(self._config)

        # Create new Karla agent (includes tool registration)
        karla_agent = create_karla_agent(
            client=client,
            config=self._config,
            working_dir=cwd,
        )

        # Update project memory block with environment context
        update_project_block(client, karla_agent.agent_id, cwd)

        # Store session state
        self._sessions[session_id] = {
            "agent_id": karla_agent.agent_id,
            "cwd": cwd,
            "client": client,
            "executor": karla_agent.executor,
        }

        logger.info("Created new session %s with Letta agent %s", session_id, karla_agent.agent_id)
        return NewSessionResponse(session_id=session_id, modes=None)

    async def load_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio],
        session_id: str,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load an existing session (session_id is the Letta agent_id)."""
        client = create_client(self._config)

        # Get existing agent
        karla_agent = get_or_create_agent(
            client=client,
            config=self._config,
            working_dir=cwd,
            agent_id=session_id,
            create_if_missing=False,
        )

        if karla_agent is None:
            logger.warning("Agent %s not found", session_id)
            return None

        self._sessions[session_id] = {
            "agent_id": karla_agent.agent_id,
            "cwd": cwd,
            "client": client,
            "executor": karla_agent.executor,
        }

        logger.info("Loaded session %s with Letta agent %s", session_id, karla_agent.agent_id)
        return LoadSessionResponse()

    async def _handle_command(
        self,
        session_id: str,
        session: dict[str, Any],
        text: str,
    ) -> PromptResponse | None:
        """Handle a slash command.

        Args:
            session_id: ACP session ID
            session: Session state dict
            text: Command text (e.g., "/clear" or "/pin")

        Returns:
            PromptResponse if command fully handled, None if should continue to agent
        """
        # Create command context
        settings = SettingsManager(session["cwd"])
        cmd_ctx = CommandContext(
            client=session["client"],
            agent_id=session["agent_id"],
            working_dir=session["cwd"],
            settings=settings,
        )

        # Dispatch the command
        result, should_continue = await dispatch_command(text, cmd_ctx)

        # Send command output as agent message
        if result:
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(result)),
            )

        # If command injected a prompt, we need to continue to agent
        if should_continue and cmd_ctx.inject_prompt:
            # TODO: Run agent loop with injected prompt
            logger.info("Command injected prompt: %s", cmd_ctx.inject_prompt)
            return None  # Continue to agent with injected prompt

        # Command fully handled
        return PromptResponse(stop_reason="end_turn")

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """Handle a prompt from the user.

        Runs the Letta agent loop with client-side tool execution,
        streaming updates back to the ACP client.
        """
        logger.info("PROMPT received for session %s", session_id)
        session = self._sessions.get(session_id)
        if not session:
            logger.error("Session %s not found", session_id)
            return PromptResponse(stop_reason="refusal")

        # Extract text from prompt blocks
        user_message = ""
        for block in prompt:
            if isinstance(block, TextContentBlock):
                user_message += block.text
            elif hasattr(block, "text"):
                user_message += getattr(block, "text", "")

        if not user_message:
            return PromptResponse(stop_reason="end_turn")

        logger.info("USER MESSAGE: %s", user_message[:100])

        # Check for slash commands
        if user_message.strip().startswith("/"):
            result = await self._handle_command(session_id, session, user_message.strip())
            if result is not None:
                return result
            # If result is None, command wants to continue to agent (e.g., injected prompt)

        # Set up context for tools
        ctx = AgentContext(
            client=session["client"],
            agent_id=session["agent_id"],
            working_dir=session["cwd"],
            llm_config=self._config.llm.to_dict(),
            embedding_config=self._config.embedding.to_string(),
            kv_cache_friendly=self._config.agent_defaults.kv_cache_friendly,
        )
        set_context(ctx)

        # Track tool calls for streaming
        tool_call_counter = [0]  # Use list for closure mutation
        text_streamed = [False]  # Track if we already streamed text

        # Track tool names for result content generation
        tool_name_cache: dict[str, str] = {}  # tc_id -> tool_name

        async def on_tool_start_async(name: str, args: dict) -> None:
            """Stream tool call start to ACP client."""
            logger.info("TOOL START: %s args=%s", name, args)
            tool_call_counter[0] += 1
            tc_id = f"tc_{tool_call_counter[0]}"
            tool_name_cache[tc_id] = name

            # Get rich tool info (title, kind, content, locations)
            info = get_tool_info(name, args)

            # Convert locations to ToolCallLocation objects
            locations = [ToolCallLocation(**loc) for loc in info.get("locations", [])]

            await self._conn.session_update(
                session_id=session_id,
                update=start_tool_call(
                    tool_call_id=tc_id,
                    title=info["title"],
                    kind=info["kind"],
                    status="in_progress",
                    locations=locations if locations else None,
                    content=info.get("content") or None,
                    raw_input=args,
                ),
            )

        async def on_tool_end_async(name: str, output: str, is_error: bool) -> None:
            """Stream tool call completion to ACP client."""
            logger.info("TOOL END: %s is_error=%s output=%s", name, is_error, output[:100] if output else "")
            tc_id = f"tc_{tool_call_counter[0]}"

            # Get result content for this tool type
            result_content = get_tool_result_content(name, output, is_error)

            await self._conn.session_update(
                session_id=session_id,
                update=update_tool_call(
                    tool_call_id=tc_id,
                    status="failed" if is_error else "completed",
                    content=result_content if result_content else None,
                    raw_output=output,
                ),
            )

        async def on_text_async(text: str) -> None:
            """Stream text response to ACP client."""
            logger.info("TEXT: %s", text[:100] if text else "")
            text_streamed[0] = True
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(text)),
            )

        try:
            # Run the agent loop with async callbacks
            response = await run_agent_loop(
                client=session["client"],
                agent_id=session["agent_id"],
                executor=session["executor"],
                message=user_message,
                max_iterations=50,
                on_tool_start=on_tool_start_async,
                on_tool_end=on_tool_end_async,
                on_text=on_text_async,
            )

            # Final text response (only if on_text wasn't called)
            if response.text and not text_streamed[0]:
                await self._conn.session_update(
                    session_id=session_id,
                    update=update_agent_message(text_block(response.text)),
                )

        except Exception as e:
            logger.exception("Error in agent loop")
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(f"Error: {e}")),
            )
        finally:
            clear_context()

        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Handle cancel notification.

        Sets the executor's cancelled flag which will:
        1. Cause any currently running tool to check and return early
        2. Cause the agent loop to exit at the next iteration check
        """
        logger.info("CANCEL received for session %s", session_id)
        session = self._sessions.get(session_id)
        if session and "executor" in session:
            session["executor"].cancel()
            logger.info("Executor cancelled flag set for session %s", session_id)
        else:
            logger.warning("Cannot cancel - session %s not found or has no executor", session_id)


async def _async_main() -> None:
    """Run the Karla ACP server (async)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config()
    agent = KarlaAgent(config)

    logger.info("Starting Karla ACP server...")
    await run_agent(agent)


def main() -> None:
    """Entry point for karla-acp command."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
