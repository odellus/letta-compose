#!/usr/bin/env python
"""Test cancellation via ACP."""

import asyncio
import json
import sys
from pathlib import Path

KARLA = Path.home() / ".local" / "bin" / "karla"


async def send_message(writer, msg):
    """Send a JSON-RPC message."""
    line = json.dumps(msg) + "\n"
    print(f">>> {json.dumps(msg)}")
    writer.write(line.encode())
    await writer.drain()


async def read_until_id(reader, target_id, timeout=120):
    """Read responses until we get one with matching id."""
    start = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start > timeout:
            print(f"!!! Timeout waiting for id={target_id}")
            return None

        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
        except asyncio.TimeoutError:
            continue

        if not line:
            print("!!! EOF")
            return None

        try:
            resp = json.loads(line)
            print(f"<<< {json.dumps(resp, indent=2)}")
            if resp.get("id") == target_id:
                return resp
        except Exception as e:
            print(f"!!! Parse error: {e}")


async def main():
    print(f"Starting {KARLA}...")

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
            print(f"[stderr] {line.decode().rstrip()}")

    stderr_task = asyncio.create_task(read_stderr())

    try:
        # 1. Initialize
        print("\n=== INITIALIZE ===")
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
        resp = await read_until_id(proc.stdout, 1)
        if not resp:
            return 1

        # 2. New session
        print("\n=== NEW SESSION ===")
        await send_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {
                "cwd": "/tmp",
                "mcpServers": []
            }
        })
        resp = await read_until_id(proc.stdout, 2, timeout=60)
        if not resp:
            return 1

        session_id = resp.get("result", {}).get("sessionId")
        print(f"Session ID: {session_id}")

        # 3. Send a prompt that will take a while (ask agent to do multiple things)
        print("\n=== PROMPT (long task) ===")
        await send_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "write a file /tmp/cancel_test.txt with 'test', then read it back, then write another file /tmp/cancel_test2.txt with 'test2'"}]
            }
        })

        # Wait a bit for the first tool to start, then cancel
        await asyncio.sleep(3)

        print("\n=== CANCEL ===")
        await send_message(proc.stdin, {
            "jsonrpc": "2.0",
            "method": "session/cancel",
            "params": {
                "sessionId": session_id
            }
        })

        # Wait for the prompt response (should come back relatively quickly with cancelled)
        resp = await read_until_id(proc.stdout, 3, timeout=60)

        print("\n=== DONE ===")

        # Check if first file was created
        test_file = Path("/tmp/cancel_test.txt")
        test_file2 = Path("/tmp/cancel_test2.txt")
        print(f"\nFile 1 exists: {test_file.exists()}")
        print(f"File 2 exists: {test_file2.exists()}")

        # Clean up
        if test_file.exists():
            test_file.unlink()
        if test_file2.exists():
            test_file2.unlink()

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
