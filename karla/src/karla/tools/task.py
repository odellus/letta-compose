"""Task tool - spawns subagents for complex tasks with HOTL support."""

import asyncio
import concurrent.futures
import logging
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Subagent type configurations
SUBAGENT_CONFIGS = {
    "general-purpose": {
        "system_prompt": """You are a general-purpose research agent. Your task is to thoroughly investigate
the given prompt and return a comprehensive answer. Use the available tools to search code,
read files, and gather information. Be thorough and provide specific file paths and line numbers
when relevant.

When you have completed the task, output <promise>DONE</promise> to signal completion.""",
        "description": "General-purpose agent for research and multi-step tasks",
        "default_max_iterations": 20,
    },
    "Explore": {
        "system_prompt": """You are a codebase exploration agent. Your task is to quickly find files,
search code for patterns, and answer questions about the codebase structure. Use Glob to find files
by pattern and Grep to search code contents. Be efficient and provide specific paths.

When you have completed the task, output <promise>DONE</promise> to signal completion.""",
        "description": "Fast agent for codebase exploration",
        "default_max_iterations": 10,
    },
    "Plan": {
        "system_prompt": """You are a software architect agent. Your task is to design implementation
plans for features or changes. Analyze the codebase to understand existing patterns and architecture.
Return a clear step-by-step plan with specific files to modify and approach recommendations.

When you have completed the task, output <promise>DONE</promise> to signal completion.""",
        "description": "Agent for designing implementation plans",
        "default_max_iterations": 15,
    },
    "Coder": {
        "system_prompt": """You are a coding agent. Your task is to implement features, fix bugs,
and write code. Use the available tools to read files, make edits, and run commands.
Follow existing patterns in the codebase. Test your changes when possible.

When you have completed the task, output <promise>DONE</promise> to signal completion.""",
        "description": "Agent for implementing code changes",
        "default_max_iterations": 30,
    },
}


class TaskTool(Tool):
    """Spawn a subagent to handle complex tasks with HOTL (Human Out of The Loop) support.

    Subagents run with full tool access and iterate until completion.
    HOTL is enabled by default - subagents keep working until they output
    <promise>DONE</promise> or hit max iterations.
    """

    def __init__(self, available_agents: list[str] | None = None) -> None:
        """Initialize with optional list of available agent types."""
        self._available_agents = available_agents or list(SUBAGENT_CONFIGS.keys())
        # Thread pool for running subagents
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        # Track running tasks
        self._tasks: dict[str, concurrent.futures.Future] = {}
        self._results: dict[str, str] = {}
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

Subagents run with HOTL (Human Out of The Loop) mode - they iterate on tasks until
completion, seeing their own previous work in files.

Available agent types:
{agent_descriptions}

When to use:
- Complex multi-step research tasks
- Codebase exploration requiring multiple searches
- Implementation tasks that need iteration
- Tasks that can run independently

When NOT to use:
- Reading a specific file (use Read)
- Searching for a specific class/function (use Grep/Glob)
- Simple, single-step operations

The subagent will keep working until it outputs <promise>DONE</promise> or hits max_iterations.""",
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
                    "max_iterations": {
                        "type": "integer",
                        "description": "Max HOTL iterations (default varies by agent type)",
                    },
                    "completion_promise": {
                        "type": "string",
                        "description": "Text that signals completion (default: DONE)",
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

        config = SUBAGENT_CONFIGS[subagent_type]
        max_iterations = args.get("max_iterations", config.get("default_max_iterations", 20))
        completion_promise = args.get("completion_promise", "DONE")

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
            subagent_id = await self._get_or_create_subagent(
                agent_ctx, subagent_type, description, ctx.working_dir
            )
        except Exception as e:
            logger.exception("Failed to create subagent")
            return ToolResult.error(f"Failed to create subagent: {e}")

        # Generate tracking ID
        tracking_id = f"task-{uuid.uuid4().hex[:8]}"

        # Register the subagent for tracking
        agent_ctx.register_subagent(
            agent_id=subagent_id,
            subagent_type=subagent_type,
            description=description,
        )

        # Submit the task to run in a thread
        future = self._executor.submit(
            self._run_subagent_with_hotl,
            agent_ctx,
            subagent_id,
            prompt,
            ctx.working_dir,
            max_iterations,
            completion_promise,
            tracking_id,
        )

        with self._lock:
            self._tasks[tracking_id] = future

        if run_in_background:
            return ToolResult.success(
                f"Subagent started in background with HOTL mode.\n"
                f"Task ID: {tracking_id}\n"
                f"Type: {subagent_type}\n"
                f"Max iterations: {max_iterations}\n"
                f"Completion promise: <promise>{completion_promise}</promise>\n\n"
                f"Use TaskOutput with task_id='{tracking_id}' to retrieve results."
            )

        # Wait for result (no timeout - HOTL loops can take a while)
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
        working_dir: str,
    ) -> str:
        """Get or create a Letta agent for the given subagent type."""
        from karla.letta import register_tools_with_letta
        from karla.tools import create_default_registry

        client = agent_ctx.client
        config = SUBAGENT_CONFIGS[subagent_type]

        # Create a unique name for this subagent
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

        # Register tools with the new subagent
        registry = create_default_registry(working_dir)
        register_tools_with_letta(client, agent.id, registry)

        return agent.id

    def _run_subagent_with_hotl(
        self,
        agent_ctx: "AgentContext",
        agent_id: str,
        prompt: str,
        working_dir: str,
        max_iterations: int,
        completion_promise: str,
        tracking_id: str,
    ) -> str:
        """Run a subagent with HOTL mode in a sync context."""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                self._run_subagent_async(
                    agent_ctx,
                    agent_id,
                    prompt,
                    working_dir,
                    max_iterations,
                    completion_promise,
                    tracking_id,
                )
            )
            return result
        finally:
            loop.close()

    async def _run_subagent_async(
        self,
        agent_ctx: "AgentContext",
        agent_id: str,
        prompt: str,
        working_dir: str,
        max_iterations: int,
        completion_promise: str,
        tracking_id: str,
    ) -> str:
        """Run a subagent with HOTL mode."""
        from karla.agent_loop import run_agent_loop
        from karla.executor import ToolExecutor
        from karla.hotl import HOTLLoop
        from karla.tools import create_default_registry

        client = agent_ctx.client

        # Create executor for the subagent
        registry = create_default_registry(working_dir)
        executor = ToolExecutor(registry, working_dir)

        # Use a temp directory for this subagent's HOTL state
        # so it doesn't interfere with the parent agent
        subagent_work_dir = Path(tempfile.mkdtemp(prefix=f"karla-subagent-{tracking_id}-"))

        # Start HOTL loop for the subagent
        hotl = HOTLLoop(str(subagent_work_dir))
        hotl.start(
            prompt=prompt,
            max_iterations=max_iterations,
            completion_promise=completion_promise,
        )

        results: list[str] = []
        current_message = prompt
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Subagent {tracking_id} iteration {iteration}/{max_iterations}")

            try:
                response = await run_agent_loop(
                    client=client,
                    agent_id=agent_id,
                    executor=executor,
                    message=current_message,
                )

                agent_output = response.text or ""
                results.append(agent_output)

                # Check for completion
                continuation = hotl.check_and_continue(agent_output)

                if not continuation:
                    # Completed (promise found or max iterations in HOTL state)
                    logger.info(f"Subagent {tracking_id} completed at iteration {iteration}")
                    break

                # Continue with same prompt
                current_message = (
                    f"<system-reminder>\n"
                    f"{continuation['status_message']}\n"
                    f"</system-reminder>\n\n"
                    f"{continuation['inject_message']}"
                )

            except Exception as e:
                logger.exception(f"Subagent {tracking_id} error at iteration {iteration}")
                results.append(f"[ERROR at iteration {iteration}]: {e}")
                break

        # Clean up HOTL state
        hotl.cancel()

        # Clean up temp directory
        try:
            import shutil
            shutil.rmtree(subagent_work_dir, ignore_errors=True)
        except Exception:
            pass

        # Mark as completed in parent context
        final_result = "\n\n---\n\n".join(results)
        agent_ctx.complete_subagent(tracking_id, final_result)

        # Store result for TaskOutput
        with self._lock:
            self._results[tracking_id] = final_result

        return final_result

    def get_task_result(
        self, task_id: str, block: bool = True, timeout: float = 30.0
    ) -> ToolResult:
        """Get the result of a background task."""
        with self._lock:
            # Check if we have a cached result
            if task_id in self._results:
                return ToolResult.success(self._results[task_id])

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
        return f"subagent ({subagent_type}): {description}{bg}"


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
