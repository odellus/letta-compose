#!/usr/bin/env python
"""Raw ACP test - sends NDJSON directly to karla process."""

import asyncio
import json
import sys
from pathlib import Path

KARLA = Path.home() / ".local" / "bin" / "karla"


async def read_responses(reader, label=""):
    """Read and print all responses from the process."""
    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
            print(f"{label}<<< {json.dumps(msg, indent=2)}")
        except:
            print(f"{label}<<< (raw) {line.decode()}")


async def send_and_wait(writer, reader, msg, timeout=30):
    """Send a message and wait for response with matching id."""
    msg_id = msg.get("id")
    line = json.dumps(msg) + "\n"
    print(f">>> {json.dumps(msg)}")
    writer.write(line.encode())
    await writer.drain()

    # Read responses until we get one with matching id
    start = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start > timeout:
            print(f"!!! Timeout waiting for response to id={msg_id}")
            return None

        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line:
            print("!!! EOF")
            return None

        try:
            resp = json.loads(line)
            print(f"<<< {json.dumps(resp, indent=2)}")

            # If it's a response to our request, return it
            if resp.get("id") == msg_id:
                return resp
            # Otherwise it's a notification, keep reading
        except Exception as e:
            print(f"!!! Parse error: {e} - {line}")


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
        resp = await send_and_wait(proc.stdin, proc.stdout, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
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

        # 3. Send prompt
        print("\n=== PROMPT ===")
        resp = await send_and_wait(proc.stdin, proc.stdout, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "say hello"}]
            }
        }, timeout=120)

        print("\n=== DONE ===")

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
