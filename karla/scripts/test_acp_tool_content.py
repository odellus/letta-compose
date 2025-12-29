#!/usr/bin/env python
"""Test rich tool content for ACP streaming - tests each tool's content output."""

import asyncio
import json
import sys
from pathlib import Path

KARLA = Path.home() / ".local" / "bin" / "karla"

# Track which tools have been tested
TOOLS_TO_TEST = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    # "WebSearch",  # Requires API key
    # "WebFetch",   # Requires network
    "TodoWrite",
]

TESTED_TOOLS = set()


async def send_message(writer, msg):
    """Send a JSON-RPC message."""
    line = json.dumps(msg) + "\n"
    print(f">>> {json.dumps(msg, indent=2)[:200]}...")
    writer.write(line.encode())
    await writer.drain()


async def collect_updates_until_id(reader, target_id, timeout=120):
    """Collect all updates until we get response with matching id."""
    updates = []
    start = asyncio.get_event_loop().time()

    while True:
        if asyncio.get_event_loop().time() - start > timeout:
            print(f"!!! Timeout waiting for id={target_id}")
            return None, updates

        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
        except asyncio.TimeoutError:
            continue

        if not line:
            print("!!! EOF")
            return None, updates

        try:
            resp = json.loads(line)

            # Collect session updates
            if resp.get("method") == "session/update":
                update = resp.get("params", {}).get("update", {})
                update_type = update.get("sessionUpdate")
                print(f"  UPDATE: {update_type}")
                updates.append(update)

            # Return when we get the response
            if resp.get("id") == target_id:
                print(f"<<< Response received for id={target_id}")
                return resp, updates

        except Exception as e:
            print(f"!!! Parse error: {e}")

    return None, updates


async def run_prompt(proc, session_id, prompt_text, msg_id):
    """Run a prompt and return all updates."""
    await send_message(proc.stdin, {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt_text}]
        }
    })
    return await collect_updates_until_id(proc.stdout, msg_id, timeout=120)


def analyze_tool_updates(updates, tool_name):
    """Analyze tool call updates for a specific tool."""
    print(f"\n=== Analyzing {tool_name} updates ===")

    tool_starts = [u for u in updates if u.get("sessionUpdate") == "tool_call"]
    tool_ends = [u for u in updates if u.get("sessionUpdate") == "tool_call_update"]

    for start in tool_starts:
        print(f"\nTool Call Start:")
        print(f"  title: {start.get('title')}")
        print(f"  kind: {start.get('kind')}")
        print(f"  status: {start.get('status')}")
        print(f"  locations: {start.get('locations')}")

        content = start.get('content')
        if content:
            print(f"  content ({len(content)} items):")
            for c in content:
                if c.get('type') == 'diff':
                    print(f"    - diff: {c.get('path')}")
                    print(f"      oldText: {repr(c.get('oldText', ''))[:50]}...")
                    print(f"      newText: {repr(c.get('newText', ''))[:50]}...")
                elif c.get('type') == 'content':
                    inner = c.get('content', {})
                    print(f"    - content: {inner.get('type')} = {repr(inner.get('text', ''))[:50]}...")
        else:
            print(f"  content: None")

    for end in tool_ends:
        print(f"\nTool Call End:")
        print(f"  status: {end.get('status')}")

        content = end.get('content')
        if content:
            print(f"  content ({len(content)} items):")
            for c in content:
                if c.get('type') == 'content':
                    inner = c.get('content', {})
                    text = inner.get('text', '')
                    print(f"    - content: {inner.get('type')} = {repr(text[:100])}...")
        else:
            print(f"  content: None (expected for Write/Edit success)")

        raw = end.get('rawOutput', '')
        print(f"  rawOutput: {repr(raw[:100])}...")

    return len(tool_starts) > 0


async def main():
    """Test each tool's rich content output."""

    # Check which tool to test from args
    if len(sys.argv) > 1:
        tool_to_test = sys.argv[1]
    else:
        tool_to_test = "Read"  # Default

    print(f"\n{'='*60}")
    print(f"Testing tool: {tool_to_test}")
    print(f"{'='*60}\n")

    proc = await asyncio.create_subprocess_exec(
        str(KARLA),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Read stderr in background
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode().rstrip()
            if "TOOL" in text or "ERROR" in text:
                print(f"[stderr] {text}")

    stderr_task = asyncio.create_task(read_stderr())

    try:
        # Initialize
        await send_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        })
        resp, _ = await collect_updates_until_id(proc.stdout, 1)
        if not resp:
            return 1

        # New session
        await send_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {
                "cwd": "/tmp",
                "mcpServers": []
            }
        })
        resp, _ = await collect_updates_until_id(proc.stdout, 2, timeout=60)
        if not resp:
            return 1

        session_id = resp.get("result", {}).get("sessionId")
        print(f"Session ID: {session_id}\n")

        # Test based on tool
        if tool_to_test == "Read":
            # Create a test file first
            Path("/tmp/test_read.txt").write_text("line 1\nline 2\nline 3\n")
            resp, updates = await run_prompt(
                proc, session_id,
                "read the file /tmp/test_read.txt",
                3
            )
            analyze_tool_updates(updates, "Read")

        elif tool_to_test == "Write":
            resp, updates = await run_prompt(
                proc, session_id,
                "write a file /tmp/test_write.txt with content 'hello world'",
                3
            )
            analyze_tool_updates(updates, "Write")

        elif tool_to_test == "Edit":
            # Create file to edit
            Path("/tmp/test_edit.txt").write_text("old content\nkeep this\n")
            resp, updates = await run_prompt(
                proc, session_id,
                "edit /tmp/test_edit.txt and replace 'old content' with 'new content'",
                3
            )
            analyze_tool_updates(updates, "Edit")

        elif tool_to_test == "Bash":
            resp, updates = await run_prompt(
                proc, session_id,
                "run the command 'echo hello'",
                3
            )
            analyze_tool_updates(updates, "Bash")

        elif tool_to_test == "Glob":
            resp, updates = await run_prompt(
                proc, session_id,
                "find all .txt files in /tmp",
                3
            )
            analyze_tool_updates(updates, "Glob")

        elif tool_to_test == "Grep":
            Path("/tmp/test_grep.txt").write_text("find me\nignore this\nfind me again\n")
            resp, updates = await run_prompt(
                proc, session_id,
                "search for 'find' in /tmp/test_grep.txt",
                3
            )
            analyze_tool_updates(updates, "Grep")

        elif tool_to_test == "TodoWrite":
            resp, updates = await run_prompt(
                proc, session_id,
                "add a todo item: 'Test the application'",
                3
            )
            analyze_tool_updates(updates, "TodoWrite")

        print(f"\n{'='*60}")
        print(f"Test complete for: {tool_to_test}")
        print(f"{'='*60}")

    finally:
        proc.terminate()
        stderr_task.cancel()
        try:
            await proc.wait()
        except:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
