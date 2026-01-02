#!/usr/bin/env python
"""Test HOTL through ACP - countdown test with max-iterations cutoff."""

import asyncio
import json
import sys
from pathlib import Path

KARLA = Path.home() / ".local" / "bin" / "karla"


async def send_and_wait(writer, reader, msg, timeout=120):
    """Send a message and wait for response with matching id."""
    msg_id = msg.get("id")
    line = json.dumps(msg) + "\n"
    print(f">>> {json.dumps(msg, indent=2)}")
    writer.write(line.encode())
    await writer.drain()

    # Read responses until we get one with matching id
    start = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start > timeout:
            print(f"!!! Timeout waiting for response to id={msg_id}")
            return None

        try:
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"!!! Read timeout")
            return None

        if not line:
            print("!!! EOF")
            return None

        try:
            resp = json.loads(line)
            # Print notifications inline
            if "method" in resp:
                # It's a notification (session/update)
                update = resp.get("params", {}).get("update", {})
                update_type = update.get("session_update", "unknown")

                if update_type == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        print(f"[agent] {content.get('text', '')}", end="", flush=True)
                elif update_type == "agent_thought_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        print(f"[thought] {content.get('text', '')}")
                elif update_type == "tool_call_start":
                    print(f"[tool] {update.get('title', 'unknown')}")
                elif update_type == "tool_call_update":
                    status = update.get("status", "")
                    if status in ("completed", "failed"):
                        print(f"[tool] -> {status}")
                else:
                    print(f"[{update_type}]")
            elif resp.get("id") == msg_id:
                # Response to our request
                print(f"\n<<< Response: {json.dumps(resp, indent=2)}")
                return resp
        except Exception as e:
            print(f"!!! Parse error: {e} - {line}")


async def main():
    print(f"Starting {KARLA}...")
    print("=" * 60)
    print("HOTL Test: Count down from 100 with max-iterations=5")
    print("=" * 60)

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
            if text and not text.startswith("INFO"):  # Skip info logs
                print(f"[stderr] {text}")

    stderr_task = asyncio.create_task(read_stderr())

    try:
        # 1. Initialize
        print("\n=== INITIALIZE ===")
        resp = await send_and_wait(proc.stdin, proc.stdout, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "hotl-test", "version": "1.0"}
            }
        })

        if not resp or "error" in resp:
            print("Initialize failed!")
            return 1

        # 2. New session
        print("\n=== NEW SESSION ===")
        resp = await send_and_wait(proc.stdin, proc.stdout, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {
                "cwd": "/tmp",
                "mcpServers": []
            }
        }, timeout=60)

        if not resp or "error" in resp:
            print("New session failed!")
            return 1

        session_id = resp.get("result", {}).get("sessionId")
        print(f"Session ID: {session_id}")

        if not session_id:
            print("No session ID!")
            return 1

        # 3. Send HOTL command
        print("\n=== HOTL COMMAND ===")
        hotl_prompt = '/hotl "Count down from 100 to 1. Each iteration, continue from where you left off. Just output numbers. You will see this prompt again after each response." --max-iterations 5 --completion-promise "COUNTDOWN_DONE"'

        resp = await send_and_wait(proc.stdin, proc.stdout, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": hotl_prompt}]
            }
        }, timeout=300)  # 5 minutes for HOTL iterations

        print("\n=== HOTL COMPLETE ===")
        print(f"Final response: {resp}")

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
