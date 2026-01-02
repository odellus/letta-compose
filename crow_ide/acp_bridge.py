"""
ACP Bridge - WebSocket to subprocess stdio bridge.

This module provides a bridge between WebSocket connections and subprocess
stdin/stdout, enabling communication with ACP-compatible agents.
"""

import asyncio
from typing import List

import websockets


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


class ACPWebSocketProxy:
    """Proxy WebSocket connections to another WebSocket server."""

    def __init__(self, target_url: str):
        """Initialize the proxy with a target WebSocket URL.

        Args:
            target_url: WebSocket URL to connect to (e.g., ws://localhost:3000).
        """
        self.target_url = target_url
        self._target_ws = None

    async def handle(self, websocket) -> None:
        """Handle a WebSocket connection by proxying to target.

        Args:
            websocket: Starlette WebSocket connection.
        """
        await websocket.accept()

        try:
            async with websockets.connect(self.target_url) as target_ws:
                self._target_ws = target_ws

                # Create tasks for bidirectional forwarding
                client_to_target = asyncio.create_task(
                    self._forward_client_to_target(websocket, target_ws)
                )
                target_to_client = asyncio.create_task(
                    self._forward_target_to_client(websocket, target_ws)
                )

                # Wait for either task to complete
                done, pending = await asyncio.wait(
                    [client_to_target, target_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        except Exception as e:
            # Send error to client if connection fails
            try:
                await websocket.send_text(f'{{"error": "Failed to connect to agent: {e}"}}')
            except:
                pass

    async def _forward_client_to_target(self, client_ws, target_ws) -> None:
        """Forward messages from client to target WebSocket."""
        async for message in client_ws.iter_text():
            await target_ws.send(message)

    async def _forward_target_to_client(self, client_ws, target_ws) -> None:
        """Forward messages from target to client WebSocket."""
        async for message in target_ws:
            await client_ws.send_text(message)
