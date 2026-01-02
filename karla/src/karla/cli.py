"""CLI for Karla coding agent.

Usage:
    karla "prompt"                    # Headless mode with prompt
    karla repl                        # Tool testing REPL
    karla --new "prompt"              # Force new agent
    karla --continue "prompt"         # Continue last agent
    karla --agent <id> "prompt"       # Use specific agent
    karla --output-format json "prompt"  # Output as JSON
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid

from karla.config import KarlaConfig, create_client, load_config
from karla.context import AgentContext, set_context, clear_context
from karla.executor import ToolExecutor
from karla.hooks import HooksManager, HooksConfig as HooksConfigRuntime
from karla.hotl import HOTLLoop
from karla.letta import register_tools_with_letta
from karla.memory import create_default_memory_blocks, get_block_ids
from karla.prompts import get_default_system_prompt, get_persona
from karla.settings import SettingsManager
from karla.tools import create_default_registry
from karla.agent_loop import run_agent_loop, format_response, OutputFormat
from karla.commands import dispatch_command, CommandContext


logger = logging.getLogger(__name__)


def create_hooks_manager(config: KarlaConfig) -> HooksManager | None:
    """Create a HooksManager from config if any hooks are defined.

    Args:
        config: Karla configuration

    Returns:
        HooksManager if hooks are defined, None otherwise
    """
    hooks_config = config.hooks
    # Check if any hooks are defined
    has_hooks = any([
        hooks_config.on_prompt_submit,
        hooks_config.on_tool_start,
        hooks_config.on_tool_end,
        hooks_config.on_message,
        hooks_config.on_loop_start,
        hooks_config.on_loop_end,
    ])
    if not has_hooks:
        return None

    # Create runtime hooks config
    runtime_config = HooksConfigRuntime(
        on_prompt_submit=hooks_config.on_prompt_submit,
        on_tool_start=hooks_config.on_tool_start,
        on_tool_end=hooks_config.on_tool_end,
        on_message=hooks_config.on_message,
        on_loop_start=hooks_config.on_loop_start,
        on_loop_end=hooks_config.on_loop_end,
    )
    return HooksManager(runtime_config)


def find_config() -> KarlaConfig:
    """Find and load karla configuration."""
    try:
        return load_config()
    except FileNotFoundError:
        print("Error: No karla.yaml found. Create one in current directory.", file=sys.stderr)
        sys.exit(1)


def create_agent(client, config: KarlaConfig, name: str | None = None, working_dir: str | None = None) -> str:
    """Create a new Karla agent.

    Args:
        client: Crow client
        config: Karla configuration
        name: Agent name (auto-generated if not provided)
        working_dir: Working directory to inject into system prompt

    Returns:
        Agent ID
    """
    if name is None:
        name = f"karla-{uuid.uuid4().hex[:8]}"

    # Default to cwd if not specified
    if working_dir is None:
        working_dir = os.getcwd()

    system_prompt = get_default_system_prompt(working_dir=working_dir)

    # Create memory blocks first
    logger.info("Creating memory blocks for agent %s", name)
    memory_blocks = create_default_memory_blocks(client)
    block_ids = get_block_ids(memory_blocks)
    logger.info("Created %d memory blocks: %s", len(block_ids), [b.label for b in memory_blocks])

    # Create the Letta agent
    agent = client.agents.create(
        name=name,
        system=system_prompt,
        llm_config=config.llm.to_dict(),
        embedding=config.embedding.to_string(),
        block_ids=block_ids,
        include_base_tools=config.agent_defaults.include_base_tools,
        kv_cache_friendly=config.agent_defaults.kv_cache_friendly,
    )

    logger.info("Created agent: %s (id=%s)", name, agent.id)

    # Attach the unified 'memory' tool for full memory management
    try:
        memory_tools = list(client.tools.list(name="memory"))
        if memory_tools:
            memory_tool = memory_tools[0]
            client.agents.tools.attach(agent_id=agent.id, tool_id=memory_tool.id)
            logger.info("Attached memory tool to agent: %s", memory_tool.id)
        else:
            logger.warning("Memory tool not found on server")
    except Exception as e:
        logger.warning("Could not attach memory tool: %s", e)

    return agent.id


def get_or_create_agent(
    client,
    config: KarlaConfig,
    settings: SettingsManager,
    agent_id: str | None = None,
    continue_last: bool = False,
    force_new: bool = False,
) -> tuple[str, bool]:
    """Get an existing agent or create a new one.

    Args:
        client: Crow client
        config: Karla configuration
        settings: Settings manager
        agent_id: Explicit agent ID to use
        continue_last: If True, continue last agent
        force_new: If True, always create new agent

    Returns:
        Tuple of (agent_id, is_new) - is_new indicates if tools need registration
    """
    # Explicit agent ID takes priority
    if agent_id:
        return agent_id, False  # Existing agent, don't re-register tools

    # Force new agent
    if force_new:
        new_id = create_agent(client, config)
        settings.save_last_agent(new_id)
        return new_id, True  # New agent, register tools

    # Try to continue last agent
    if continue_last:
        last = settings.get_last_agent()
        if last:
            # Verify agent still exists
            try:
                client.agents.retrieve(last)
                return last, False  # Existing agent, don't re-register tools
            except Exception:
                logger.warning("Last agent %s not found, creating new", last)

    # Default: create new agent
    new_id = create_agent(client, config)
    settings.save_last_agent(new_id)
    return new_id, True  # New agent, register tools


async def headless_mode(
    prompt: str,
    config: KarlaConfig,
    working_dir: str,
    agent_id: str | None = None,
    continue_last: bool = False,
    force_new: bool = False,
    output_format: str = "text",
    model_override: str | None = None,
) -> int:
    """Run Karla in headless mode.

    Args:
        prompt: User prompt to send
        config: Karla configuration
        working_dir: Working directory for tools
        agent_id: Explicit agent ID
        continue_last: Continue last agent
        force_new: Force new agent
        output_format: Output format (text, json, stream-json)
        model_override: Override model from config

    Returns:
        Exit code (0 = success)
    """
    # Apply model override if provided
    if model_override:
        config.llm.model = model_override

    client = create_client(config)
    settings = SettingsManager(project_dir=working_dir)

    # Get or create agent
    agent_id, is_new = get_or_create_agent(
        client, config, settings,
        agent_id=agent_id,
        continue_last=continue_last,
        force_new=force_new,
    )

    # Create registry and only register tools for new agents
    # Re-registering tools on existing agents causes prompt regeneration
    # which breaks KV cache (LCP similarity drops from ~100% to ~26%)
    registry = create_default_registry(working_dir)
    if is_new:
        register_tools_with_letta(client, agent_id, registry)

    # Create executor
    executor = ToolExecutor(registry, working_dir)

    # Create hooks manager if configured
    hooks_manager = create_hooks_manager(config)

    # Set up agent context for tools that need it (Task, Skill, etc.)
    agent_ctx = AgentContext(
        client=client,
        agent_id=agent_id,
        working_dir=working_dir,
        llm_config=config.llm.to_dict(),
        embedding_config=config.embedding.to_string(),
        kv_cache_friendly=config.agent_defaults.kv_cache_friendly,
    )
    set_context(agent_ctx)

    # Parse output format
    try:
        fmt = OutputFormat(output_format)
    except ValueError:
        print(f"Invalid output format: {output_format}", file=sys.stderr)
        return 1

    # Callbacks for output
    def on_text(text: str):
        if fmt == OutputFormat.TEXT:
            print(text)

    def on_tool_start(name: str, args: dict):
        if fmt == OutputFormat.TEXT:
            print(f"[{name}]", file=sys.stderr)

    def on_tool_end(name: str, output: str, is_error: bool):
        pass  # Silent in headless mode

    # Run the agent loop
    try:
        response = await run_agent_loop(
            client=client,
            agent_id=agent_id,
            executor=executor,
            message=prompt,
            on_text=on_text,
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
            hooks_manager=hooks_manager,
        )

        # Format and output
        if fmt != OutputFormat.TEXT:
            print(format_response(response, fmt))

        clear_context()
        return 0

    except Exception as e:
        logger.exception("Error in agent loop")
        print(f"Error: {e}", file=sys.stderr)
        clear_context()
        return 1


async def test_tool(registry, working_dir: str, tool_name: str, args_str: str):
    """Test a single tool execution."""
    import json

    executor = ToolExecutor(registry, working_dir)

    try:
        args = json.loads(args_str) if args_str else {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return

    print(f"Executing {tool_name} with args: {args}")
    print("-" * 40)

    result = await executor.execute(tool_name, args)

    if result.is_error:
        print(f"ERROR: {result.output}")
    else:
        print(result.output)

    if result.stdout:
        print(f"\n[stdout]\n{result.stdout}")
    if result.stderr:
        print(f"\n[stderr]\n{result.stderr}")


async def run_with_hotl(
    client,
    agent_id: str,
    executor,
    message: str,
    working_dir: str,
    on_text=None,
    on_tool_start=None,
    on_tool_end=None,
    hooks_manager=None,
) -> None:
    """Run agent loop with HOTL (Human Out of The Loop) support.

    After each agent loop iteration, checks if HOTL mode is active
    and if so, continues with the same prompt until completion.
    """
    hotl = HOTLLoop(working_dir)
    current_message = message

    while True:
        try:
            response = await run_agent_loop(
                client=client,
                agent_id=agent_id,
                executor=executor,
                message=current_message,
                on_text=on_text,
                on_tool_start=on_tool_start,
                on_tool_end=on_tool_end,
                hooks_manager=hooks_manager,
            )

            # Check if HOTL should continue
            agent_output = response.text or ""
            continuation = hotl.check_and_continue(agent_output)

            if continuation:
                # Print HOTL status
                print(f"\n{continuation['status_message']}\n")
                # Continue with injected message
                current_message = (
                    f"<system-reminder>\n"
                    f"{continuation['status_message']}\n"
                    f"</system-reminder>\n\n"
                    f"{continuation['inject_message']}"
                )
            else:
                # No HOTL or HOTL complete
                break

        except Exception as e:
            logger.exception("Error in agent loop")
            print(f"Error: {e}")
            break


async def interactive_mode(
    config: KarlaConfig,
    working_dir: str,
    agent_id: str | None = None,
    continue_last: bool = False,
    force_new: bool = False,
    model_override: str | None = None,
) -> int:
    """Run Karla in interactive chat mode with slash command support.

    Args:
        config: Karla configuration
        working_dir: Working directory for tools
        agent_id: Explicit agent ID
        continue_last: Continue last agent
        force_new: Force new agent
        model_override: Override model from config

    Returns:
        Exit code (0 = success)
    """
    # Apply model override if provided
    if model_override:
        config.llm.model = model_override

    client = create_client(config)
    settings = SettingsManager(project_dir=working_dir)

    # Get or create agent
    agent_id, is_new = get_or_create_agent(
        client, config, settings,
        agent_id=agent_id,
        continue_last=continue_last,
        force_new=force_new,
    )

    # Create registry and only register tools for new agents
    registry = create_default_registry(working_dir)
    if is_new:
        register_tools_with_letta(client, agent_id, registry)

    # Create executor
    executor = ToolExecutor(registry, working_dir)

    # Create hooks manager if configured
    hooks_manager = create_hooks_manager(config)

    # Set up agent context for tools that need it (Task, Skill, etc.)
    agent_ctx = AgentContext(
        client=client,
        agent_id=agent_id,
        working_dir=working_dir,
        llm_config=config.llm.to_dict(),
        embedding_config=config.embedding.to_string(),
        kv_cache_friendly=config.agent_defaults.kv_cache_friendly,
    )
    set_context(agent_ctx)

    # Create command context
    ctx = CommandContext(
        client=client,
        agent_id=agent_id,
        working_dir=working_dir,
        settings=settings,
    )

    # Print welcome message
    agent = client.agents.retrieve(agent_id)
    print(f"Karla Interactive Mode")
    print(f"Agent: {agent.name} ({agent_id})")
    print(f"Working directory: {working_dir}")
    print("Type /help for commands, /exit to quit")
    print()

    # Callbacks for output
    def on_text(text: str):
        print(f"karla> {text}")

    def on_tool_start(name: str, args: dict):
        print(f"  [{name}]", end="", flush=True)

    def on_tool_end(name: str, output: str, is_error: bool):
        if is_error:
            print(" ERROR")
        else:
            print(" done")

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Check for slash commands
        if user_input.startswith("/"):
            output, continue_to_agent = await dispatch_command(user_input, ctx)
            print(output)

            if user_input == "/exit":
                break

            # If command injected a prompt, send it to agent (with HOTL support)
            if continue_to_agent and ctx.inject_prompt:
                await run_with_hotl(
                    client=client,
                    agent_id=ctx.agent_id,
                    executor=executor,
                    message=ctx.inject_prompt,
                    working_dir=ctx.working_dir,
                    on_text=on_text,
                    on_tool_start=on_tool_start,
                    on_tool_end=on_tool_end,
                    hooks_manager=hooks_manager,
                )
                ctx.inject_prompt = None

            continue

        # Regular message to agent (with HOTL support)
        await run_with_hotl(
            client=client,
            agent_id=ctx.agent_id,
            executor=executor,
            message=user_input,
            working_dir=ctx.working_dir,
            on_text=on_text,
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
            hooks_manager=hooks_manager,
        )

    # Clean up context
    clear_context()
    return 0


async def repl(registry, working_dir: str):
    """Interactive REPL for testing tools."""
    import json

    executor = ToolExecutor(registry, working_dir)

    print("Karla Tool REPL")
    print(f"Working directory: {working_dir}")
    print(f"Available tools: {', '.join(registry.list_tools())}")
    print("\nUsage: <tool_name> <json_args>")
    print('Example: Read {"file_path": "/path/to/file.py"}')
    print("Type 'quit' or 'exit' to exit.\n")

    while True:
        try:
            line = input("karla> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not line:
            continue

        if line.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if line.lower() == "tools":
            for tool in registry:
                defn = tool.definition()
                print(f"  {defn.name}: {defn.description.split(chr(10))[0]}")
            continue

        if line.lower() == "help":
            print("Commands:")
            print("  tools      - List available tools")
            print("  <tool> {}  - Execute a tool with JSON args")
            print("  quit/exit  - Exit the REPL")
            continue

        # Parse tool name and args
        parts = line.split(None, 1)
        tool_name = parts[0]
        args_str = parts[1] if len(parts) > 1 else "{}"

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            continue

        result = await executor.execute(tool_name, args)

        if result.is_error:
            print(f"ERROR: {result.output}")
        else:
            print(result.output)
        print()


def _parse_chat_args(args: list[str]) -> dict:
    """Parse args for chat subcommand."""
    result = {
        "working_dir": os.getcwd(),
        "agent_id": None,
        "continue_last": False,
        "force_new": False,
        "model": None,
        "verbose": False,
    }

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-d", "--working-dir") and i + 1 < len(args):
            result["working_dir"] = os.path.abspath(args[i + 1])
            i += 2
        elif arg in ("-a", "--agent") and i + 1 < len(args):
            result["agent_id"] = args[i + 1]
            i += 2
        elif arg in ("-c", "--continue"):
            result["continue_last"] = True
            i += 1
        elif arg in ("-n", "--new"):
            result["force_new"] = True
            i += 1
        elif arg in ("-m", "--model") and i + 1 < len(args):
            result["model"] = args[i + 1]
            i += 2
        elif arg in ("-v", "--verbose"):
            result["verbose"] = True
            i += 1
        else:
            i += 1

    return result


def _handle_subcommand(command: str, args: list[str]):
    """Handle subcommands (chat, repl, test, list)."""
    working_dir = os.getcwd()

    # Parse working-dir if provided
    for i, arg in enumerate(args):
        if arg in ("-d", "--working-dir") and i + 1 < len(args):
            working_dir = os.path.abspath(args[i + 1])
            break

    if command == "chat":
        # Parse chat-specific args
        parsed = _parse_chat_args(args)

        if parsed["verbose"]:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.WARNING)

        config = find_config()
        exit_code = asyncio.run(interactive_mode(
            config=config,
            working_dir=parsed["working_dir"],
            agent_id=parsed["agent_id"],
            continue_last=parsed["continue_last"],
            force_new=parsed["force_new"],
            model_override=parsed["model"],
        ))
        sys.exit(exit_code)

    registry = create_default_registry(working_dir)

    if command == "list":
        print("Available tools:")
        for tool in registry:
            defn = tool.definition()
            print(f"  {defn.name}")
            first_line = defn.description.split("\n")[0]
            print(f"    {first_line}")
        return

    if command == "repl":
        asyncio.run(repl(registry, working_dir))
        return

    if command == "test":
        if not args:
            print("Usage: karla test <tool_name> [json_args]", file=sys.stderr)
            sys.exit(1)
        tool_name = args[0]
        tool_args = args[1] if len(args) > 1 else "{}"
        asyncio.run(test_tool(registry, working_dir, tool_name, tool_args))
        return


def main():
    # Check for subcommands first (before argparse to avoid conflicts)
    subcommands = {"chat", "repl", "test", "list"}

    # If first non-flag arg is a subcommand, handle it separately
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        _handle_subcommand(sys.argv[1], sys.argv[2:])
        return

    # Main parser for headless mode
    parser = argparse.ArgumentParser(
        description="Karla - Python coding agent with Crow backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  karla "Create a hello.py file"          Run single prompt
  karla --continue "Add a function"       Continue last agent
  karla --new "Start fresh project"       Force new agent
  karla chat                              Interactive mode with slash commands
  karla chat --continue                   Continue last agent interactively
  karla repl                              Tool testing REPL
  karla list                              List available tools
""",
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Prompt to send to the agent (headless mode)",
    )
    parser.add_argument(
        "--working-dir", "-d",
        default=os.getcwd(),
        help="Working directory for tools (default: current dir)",
    )
    parser.add_argument(
        "--agent", "-a",
        help="Use specific agent ID",
    )
    parser.add_argument(
        "--continue", "-c",
        dest="continue_last",
        action="store_true",
        help="Continue last agent session",
    )
    parser.add_argument(
        "--new", "-n",
        action="store_true",
        help="Force creation of new agent",
    )
    parser.add_argument(
        "--output-format", "-o",
        choices=["text", "json", "stream-json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--model", "-m",
        help="Override model (e.g., 'gpt-4', 'claude-3-opus')",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    working_dir = os.path.abspath(args.working_dir)

    # Headless mode - requires prompt
    if args.prompt:
        config = find_config()
        exit_code = asyncio.run(headless_mode(
            prompt=args.prompt,
            config=config,
            working_dir=working_dir,
            agent_id=args.agent,
            continue_last=args.continue_last,
            force_new=args.new,
            output_format=args.output_format,
            model_override=args.model,
        ))
        sys.exit(exit_code)

    # No prompt - show help
    parser.print_help()


if __name__ == "__main__":
    main()
