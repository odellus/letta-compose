"""
ACP Bridge - WebSocket to subprocess stdio bridge.

This module provides a bridge between WebSocket connections and subprocess
stdin/stdout, enabling communication with ACP-compatible agents.
"""

import asyncio
from typing import List


class ACPBridge:
    """Bridge WebSocket connections to subprocess stdio."""

    def __init__(self, command: List[str]):
        """Initialize the bridge with a command to run.

        Args:
            command: Command and arguments to spawn as subprocess.
        """
        self.command = command
        self._process = None

    async def handle(self, websocket) -> None:
        """Handle a WebSocket connection by bridging to subprocess.

        Args:
            websocket: Starlette WebSocket connection.
        """
        await websocket.accept()

        # Spawn the subprocess
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Create tasks for reading from stdout and websocket
        stdout_task = asyncio.create_task(self._forward_stdout(websocket))
        ws_task = asyncio.create_task(self._forward_websocket(websocket))

        try:
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [stdout_task, ws_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if self._process:
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass

    async def _forward_stdout(self, websocket) -> None:
        """Forward subprocess stdout to WebSocket.

        Args:
            websocket: Starlette WebSocket connection.
        """
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            # Decode and send to websocket
            text = line.decode('utf-8').rstrip('\n')
            if text:
                await websocket.send_text(text)

    async def _forward_websocket(self, websocket) -> None:
        """Forward WebSocket messages to subprocess stdin.

        Args:
            websocket: Starlette WebSocket connection.
        """
        async for message in websocket.iter_text():
            # Write to subprocess stdin
            data = message.encode('utf-8')
            if not data.endswith(b'\n'):
                data += b'\n'
            self._process.stdin.write(data)
            await self._process.stdin.drain()
