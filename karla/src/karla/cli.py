"""Simple CLI/REPL for testing karla."""

import argparse
import asyncio
import os
import sys

from karla.executor import ToolExecutor
from karla.registry import ToolRegistry
from karla.tools import create_default_registry


async def test_tool(registry: ToolRegistry, working_dir: str, tool_name: str, args_str: str):
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


async def repl(registry: ToolRegistry, working_dir: str):
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


def main():
    parser = argparse.ArgumentParser(description="Karla tool testing CLI")
    parser.add_argument(
        "--working-dir",
        "-d",
        default=os.getcwd(),
        help="Working directory for tools",
    )

    subparsers = parser.add_subparsers(dest="command")

    # REPL command
    subparsers.add_parser("repl", help="Start interactive REPL")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test a single tool")
    test_parser.add_argument("tool", help="Tool name to test")
    test_parser.add_argument("args", nargs="?", default="{}", help="JSON arguments")

    # List command
    subparsers.add_parser("list", help="List available tools")

    args = parser.parse_args()

    working_dir = os.path.abspath(args.working_dir)
    registry = create_default_registry(working_dir)

    if args.command == "list":
        print("Available tools:")
        for tool in registry:
            defn = tool.definition()
            print(f"  {defn.name}")
            # Print first line of description
            first_line = defn.description.split("\n")[0]
            print(f"    {first_line}")
        return

    if args.command == "test":
        asyncio.run(test_tool(registry, working_dir, args.tool, args.args))
        return

    if args.command == "repl" or args.command is None:
        asyncio.run(repl(registry, working_dir))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
