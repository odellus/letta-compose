"""Task tool - spawns subagents for complex tasks using Letta."""

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Subagent type configurations
SUBAGENT_CONFIGS = {
    "general-purpose": {
        "system_prompt": """You are a general-purpose research agent. Your task is to thoroughly investigate
the given prompt and return a comprehensive answer. Use the available tools to search code,
read files, and gather information. Be thorough and provide specific file paths and line numbers
when relevant.""",
        "description": "General-purpose agent for research and multi-step tasks",
    },
    "Explore": {
        "system_prompt": """You are a codebase exploration agent. Your task is to quickly find files,
search code for patterns, and answer questions about the codebase structure. Use Glob to find files
by pattern and Grep to search code contents. Be efficient and provide specific paths.""",
        "description": "Fast agent for codebase exploration",
    },
    "Plan": {
        "system_prompt": """You are a software architect agent. Your task is to design implementation
plans for features or changes. Analyze the codebase to understand existing patterns and architecture.
Return a clear step-by-step plan with specific files to modify and approach recommendations.""",
        "description": "Agent for designing implementation plans",
    },
}


class TaskTool(Tool):
    """Spawn a subagent to handle complex tasks using Letta.

    This tool creates a new Letta agent (or reuses one) and runs it
    in a background thread. Results can be retrieved immediately
    (blocking) or later via TaskOutput.
    """

    def __init__(self, available_agents: list[str] | None = None) -> None:
        """Initialize with optional list of available agent types."""
        self._available_agents = available_agents or list(SUBAGENT_CONFIGS.keys())
        # Thread pool for running subagents
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        # Track running tasks
        self._tasks: dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Task"

    def definition(self) -> ToolDefinition:
        agent_descriptions = "\n".join(
            f"- {name}: {cfg['description']}"
            for name, cfg in SUBAGENT_CONFIGS.items()
            if name in self._available_agents
        )

        return ToolDefinition(
            name="Task",
            description=f"""Launch a subagent to handle complex, multi-step tasks autonomously.

Available agent types:
{agent_descriptions}

When to use:
- Complex multi-step research tasks
- Codebase exploration requiring multiple searches
- Tasks that can run independently while you continue other work

When NOT to use:
- Reading a specific file (use Read)
- Searching for a specific class/function (use Grep/Glob)
- Simple, single-step operations

Usage notes:
- Launch multiple agents concurrently for independent tasks
- Provide clear, detailed prompts
- Use run_in_background=true for tasks you don't need immediately""",
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "A short (3-5 word) description of the task",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Detailed task description for the subagent",
                    },
                    "subagent_type": {
                        "type": "string",
                        "description": "Type of specialized agent to use",
                        "enum": self._available_agents,
                    },
                    "run_in_background": {
                        "type": "boolean",
                        "description": "Run in background (use TaskOutput to get results later)",
                    },
                },
                "required": ["description", "prompt", "subagent_type"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        description = args.get("description")
        prompt = args.get("prompt")
        subagent_type = args.get("subagent_type")
        run_in_background = args.get("run_in_background", False)

        if not description:
            return ToolResult.error("description is required")
        if not prompt:
            return ToolResult.error("prompt is required")
        if not subagent_type:
            return ToolResult.error("subagent_type is required")

        if subagent_type not in self._available_agents:
            return ToolResult.error(
                f"Unknown subagent_type: {subagent_type}. "
                f"Available: {', '.join(self._available_agents)}"
            )

        # Get the agent context
        try:
            from karla.context import get_context

            agent_ctx = get_context()
        except RuntimeError:
            return ToolResult.error(
                "No agent context available. Task tool requires Letta integration."
            )

        # Create or get subagent
        try:
            subagent_id = await self._get_or_create_subagent(agent_ctx, subagent_type, description)
        except Exception as e:
            logger.exception("Failed to create subagent")
            return ToolResult.error(f"Failed to create subagent: {e}")

        # Register the subagent for tracking
        tracking_id = agent_ctx.register_subagent(
            agent_id=subagent_id,
            subagent_type=subagent_type,
            description=description,
        )

        # Submit the task to run in a thread
        future = self._executor.submit(
            self._run_subagent_sync,
            agent_ctx.client,
            subagent_id,
            prompt,
            tracking_id,
            agent_ctx,
        )

        with self._lock:
            self._tasks[tracking_id] = future

        if run_in_background:
            return ToolResult.success(
                f"Subagent started in background.\n"
                f"Task ID: {tracking_id}\n"
                f"Type: {subagent_type}\n"
                f"Description: {description}\n\n"
                f"Use TaskOutput with task_id='{tracking_id}' to retrieve results."
            )

        # Wait for result (no timeout - LLMs can be slow)
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                future.result,
            )
            return ToolResult.success(result)
        except Exception as e:
            logger.exception("Subagent execution failed")
            return ToolResult.error(f"Subagent failed: {e}")

    async def _get_or_create_subagent(
        self,
        agent_ctx: "AgentContext",
        subagent_type: str,
        description: str,
    ) -> str:
        """Get or create a Letta agent for the given subagent type."""
        from karla.context import AgentContext

        client = agent_ctx.client
        config = SUBAGENT_CONFIGS[subagent_type]

        # Create a unique name for this subagent
        # In practice, you might want to reuse agents by type
        agent_name = f"karla-{subagent_type.lower()}-subagent"

        # Try to find existing agent
        try:
            agents = client.agents.list()
            for agent in agents:
                if agent.name == agent_name:
                    logger.info(f"Reusing existing subagent: {agent.id}")
                    return agent.id
        except Exception as e:
            logger.warning(f"Failed to list agents: {e}")

        # Create new agent with inherited LLM config
        logger.info(f"Creating new subagent: {agent_name}")

        create_kwargs = {
            "name": agent_name,
            "system": config["system_prompt"],
            "include_base_tools": True,
            "kv_cache_friendly": agent_ctx.kv_cache_friendly,
        }

        # Inherit LLM config from parent if available
        if agent_ctx.llm_config:
            create_kwargs["llm_config"] = agent_ctx.llm_config

        # Inherit embedding config from parent if available
        if agent_ctx.embedding_config:
            create_kwargs["embedding"] = agent_ctx.embedding_config

        agent = client.agents.create(**create_kwargs)

        return agent.id

    def _run_subagent_sync(
        self,
        client: "Letta",
        agent_id: str,
        prompt: str,
        tracking_id: str,
        agent_ctx: "AgentContext",
    ) -> str:
        """Run a subagent synchronously (called from thread pool)."""
        try:
            # Send message to subagent and get response
            response = client.agents.messages.create(
                agent_id=agent_id,
                input=prompt,
            )

            # Extract the text response
            result_parts = []
            for msg in response.messages:
                # Handle different message types
                if hasattr(msg, "content") and msg.content:
                    result_parts.append(msg.content)
                elif hasattr(msg, "reasoning") and msg.reasoning:
                    result_parts.append(f"[Reasoning] {msg.reasoning}")

            result = "\n\n".join(result_parts) if result_parts else "(no response)"

            # Mark as completed
            agent_ctx.complete_subagent(tracking_id, result)

            return result

        except Exception as e:
            error_msg = str(e)
            agent_ctx.fail_subagent(tracking_id, error_msg)
            raise

    def get_task_result(
        self, task_id: str, block: bool = True, timeout: float = 30.0
    ) -> ToolResult:
        """Get the result of a background task.

        Args:
            task_id: The task tracking ID
            block: Whether to wait for completion
            timeout: How long to wait (in seconds) if blocking

        Returns:
            ToolResult with task output or status
        """
        with self._lock:
            future = self._tasks.get(task_id)

        if future is None:
            return ToolResult.error(f"Unknown task ID: {task_id}")

        if not block:
            if future.done():
                try:
                    result = future.result(timeout=0)
                    return ToolResult.success(result)
                except Exception as e:
                    return ToolResult.error(f"Task failed: {e}")
            else:
                return ToolResult.success(f"Task {task_id} is still running...")

        # Block until done
        try:
            result = future.result(timeout=timeout)
            return ToolResult.success(result)
        except concurrent.futures.TimeoutError:
            return ToolResult.success(
                f"Task {task_id} is still running after {timeout}s. "
                "Use block=false to check status without waiting."
            )
        except Exception as e:
            return ToolResult.error(f"Task failed: {e}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        description = args.get("description", "task")
        subagent_type = args.get("subagent_type", "agent")
        bg = " (background)" if args.get("run_in_background") else ""
        return f"task ({subagent_type}): {description}{bg}"


class TaskOutputTool(Tool):
    """Retrieve output from a background task."""

    def __init__(self, task_tool: TaskTool) -> None:
        self._task_tool = task_tool

    @property
    def name(self) -> str:
        return "TaskOutput"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="TaskOutput",
            description="""Retrieve output from a running or completed background task.

Use this to get results from tasks started with run_in_background=true.

Args:
    task_id: The task ID returned when the task was started
    block: Whether to wait for completion (default true)
    timeout: How long to wait in milliseconds (default 30000, max 600000)""",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to get output from",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "Whether to wait for completion (default true)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max wait time in ms (default 30000)",
                    },
                },
                "required": ["task_id"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        task_id = args.get("task_id")
        if not task_id:
            return ToolResult.error("task_id is required")

        block = args.get("block", True)
        timeout_ms = args.get("timeout", 30000)
        timeout_s = min(timeout_ms / 1000, 600)  # Cap at 10 minutes

        return self._task_tool.get_task_result(task_id, block=block, timeout=timeout_s)

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        task_id = args.get("task_id", "unknown")
        return f"task output: {task_id}"
