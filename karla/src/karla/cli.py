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
from karla.executor import ToolExecutor
from karla.letta import register_tools_with_letta
from karla.memory import create_default_memory_blocks, get_block_ids
from karla.prompts import get_default_system_prompt, get_persona
from karla.settings import SettingsManager
from karla.tools import create_default_registry
from karla.agent_loop import run_agent_loop, format_response, OutputFormat


logger = logging.getLogger(__name__)


def find_config() -> KarlaConfig:
    """Find and load karla configuration."""
    try:
        return load_config()
    except FileNotFoundError:
        print("Error: No karla.yaml found. Create one in current directory.", file=sys.stderr)
        sys.exit(1)


def create_agent(client, config: KarlaConfig, name: str | None = None) -> str:
    """Create a new Karla agent.

    Args:
        client: Letta client
        config: Karla configuration
        name: Agent name (auto-generated if not provided)

    Returns:
        Agent ID
    """
    if name is None:
        name = f"karla-{uuid.uuid4().hex[:8]}"

    system_prompt = get_default_system_prompt()

    # Create memory blocks first
    logger.info("Creating memory blocks for agent %s", name)
    memory_blocks = create_default_memory_blocks(client)
    block_ids = get_block_ids(memory_blocks)
    logger.info("Created %d memory blocks: %s", len(block_ids), [b.label for b in memory_blocks])

    agent = client.agents.create(
        name=name,
        system=system_prompt,
        llm_config=config.llm.to_dict(),
        embedding=config.embedding.to_string(),
        block_ids=block_ids,
        include_base_tools=config.agent_defaults.include_base_tools,
        kv_cache_friendly=config.agent_defaults.kv_cache_friendly,
    )

    # Attach the memory tool for full memory management
    # (memory_read/insert/replace come from sleeptime, but unified memory tool is separate)
    try:
        memory_tools_response = client.tools.list(name="memory")
        # Handle paginated response
        memory_tools = list(memory_tools_response) if memory_tools_response else []
        if memory_tools:
            memory_tool = memory_tools[0]
            client.agents.tools.attach(agent_id=agent.id, tool_id=memory_tool.id)
            logger.info("Attached memory tool to agent")
    except Exception as e:
        logger.warning("Could not attach memory tool: %s", e)

    logger.info("Created agent: %s (id=%s)", name, agent.id)
    return agent.id


def get_or_create_agent(
    client,
    config: KarlaConfig,
    settings: SettingsManager,
    agent_id: str | None = None,
    continue_last: bool = False,
    force_new: bool = False,
) -> str:
    """Get an existing agent or create a new one.

    Args:
        client: Letta client
        config: Karla configuration
        settings: Settings manager
        agent_id: Explicit agent ID to use
        continue_last: If True, continue last agent
        force_new: If True, always create new agent

    Returns:
        Agent ID to use
    """
    # Explicit agent ID takes priority
    if agent_id:
        return agent_id

    # Force new agent
    if force_new:
        new_id = create_agent(client, config)
        settings.save_last_agent(new_id)
        return new_id

    # Try to continue last agent
    if continue_last:
        last = settings.get_last_agent()
        if last:
            # Verify agent still exists
            try:
                client.agents.retrieve(last)
                return last
            except Exception:
                logger.warning("Last agent %s not found, creating new", last)

    # Default: create new agent
    new_id = create_agent(client, config)
    settings.save_last_agent(new_id)
    return new_id


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
    agent_id = get_or_create_agent(
        client, config, settings,
        agent_id=agent_id,
        continue_last=continue_last,
        force_new=force_new,
    )

    # Create registry and register tools
    registry = create_default_registry(working_dir)
    register_tools_with_letta(client, agent_id, registry)

    # Create executor
    executor = ToolExecutor(registry, working_dir)

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
        )

        # Format and output
        if fmt != OutputFormat.TEXT:
            print(format_response(response, fmt))

        return 0

    except Exception as e:
        logger.exception("Error in agent loop")
        print(f"Error: {e}", file=sys.stderr)
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


def _handle_subcommand(command: str, args: list[str]):
    """Handle subcommands (repl, test, list)."""
    working_dir = os.getcwd()

    # Parse working-dir if provided
    for i, arg in enumerate(args):
        if arg in ("-d", "--working-dir") and i + 1 < len(args):
            working_dir = os.path.abspath(args[i + 1])
            break

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
    subcommands = {"repl", "test", "list"}

    # If first non-flag arg is a subcommand, handle it separately
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        _handle_subcommand(sys.argv[1], sys.argv[2:])
        return

    # Main parser for headless mode
    parser = argparse.ArgumentParser(
        description="Karla - Python coding agent with Letta backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  karla "Create a hello.py file"          Run single prompt
  karla --continue "Add a function"       Continue last agent
  karla --new "Start fresh project"       Force new agent
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
