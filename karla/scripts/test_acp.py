#!/usr/bin/env python
"""Test ACP client for Karla - shows all session updates."""

import asyncio
import asyncio.subprocess as aio_subprocess
import os
import sys
from pathlib import Path
from typing import Any

# Add python-sdk to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "python-sdk" / "src"))

from acp import PROTOCOL_VERSION, Client, RequestError, connect_to_agent, text_block
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    ClientCapabilities,
    CurrentModeUpdate,
    Implementation,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UserMessageChunk,
)


class TestClient(Client):
    """Test client that prints all session updates."""

    async def session_update(
        self,
        session_id: str,
        update: UserMessageChunk
        | AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | AgentPlanUpdate
        | AvailableCommandsUpdate
        | CurrentModeUpdate,
        **kwargs: Any,
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                print(f"\n[AGENT] {content.text}")
            else:
                print(f"\n[AGENT] <{type(content).__name__}>")

        elif isinstance(update, ToolCallStart):
            print(f"\n[TOOL START] {update.title} (id={update.tool_call_id})")
            print(f"  kind: {update.kind}")
            print(f"  status: {update.status}")
            if update.locations:
                print(f"  locations: {[loc.path for loc in update.locations]}")
            if update.raw_input:
                import json
                print(f"  input: {json.dumps(update.raw_input, indent=4)[:200]}")

        elif isinstance(update, ToolCallProgress):
            print(f"\n[TOOL UPDATE] id={update.tool_call_id}")
            print(f"  status: {update.status}")
            if update.raw_output:
                output = str(update.raw_output)[:200]
                print(f"  output: {output}{'...' if len(str(update.raw_output)) > 200 else ''}")

        elif isinstance(update, AgentThoughtChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                print(f"\n[THOUGHT] {content.text}")

        else:
            print(f"\n[{type(update).__name__}] {update}")

    # Stub out other required methods
    async def request_permission(self, **kwargs): raise RequestError.method_not_found("request_permission")
    async def write_text_file(self, **kwargs): raise RequestError.method_not_found("write_text_file")
    async def read_text_file(self, **kwargs): raise RequestError.method_not_found("read_text_file")
    async def create_terminal(self, **kwargs): raise RequestError.method_not_found("create_terminal")
    async def terminal_output(self, **kwargs): raise RequestError.method_not_found("terminal_output")
    async def release_terminal(self, **kwargs): raise RequestError.method_not_found("release_terminal")
    async def wait_for_terminal_exit(self, **kwargs): raise RequestError.method_not_found("wait_for_terminal_exit")
    async def kill_terminal(self, **kwargs): raise RequestError.method_not_found("kill_terminal")
    async def ext_method(self, **kwargs): raise RequestError.method_not_found("ext_method")
    async def ext_notification(self, **kwargs): pass


async def main():
    # Start karla ACP server
    karla_path = Path.home() / ".local" / "bin" / "karla"

    print(f"Starting Karla ACP server: {karla_path}")
    proc = await asyncio.create_subprocess_exec(
        str(karla_path),
        stdin=aio_subprocess.PIPE,
        stdout=aio_subprocess.PIPE,
        stderr=aio_subprocess.PIPE,
    )

    if proc.stdin is None or proc.stdout is None:
        print("Failed to open pipes", file=sys.stderr)
        return 1

    client = TestClient()
    conn = connect_to_agent(client, proc.stdin, proc.stdout)

    print("Initializing...")
    resp = await conn.initialize(
        protocol_version=PROTOCOL_VERSION,
        client_capabilities=ClientCapabilities(),
        client_info=Implementation(name="test-client", title="Test Client", version="0.1.0"),
    )
    print(f"Agent: {resp.agent_info.name} v{resp.agent_info.version}")

    print("Creating session...")
    session = await conn.new_session(mcp_servers=[], cwd=os.getcwd())
    print(f"Session: {session.session_id}")

    # Interactive loop
    print("\nReady. Type messages (Ctrl+D to quit):\n")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        try:
            await conn.prompt(session_id=session.session_id, prompt=[text_block(line)])
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

    proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
