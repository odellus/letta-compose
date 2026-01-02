"""
Crow IDE Server - Starlette-based web server.

Provides HTTP and WebSocket endpoints for the IDE.
"""

import os
from pathlib import Path
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse
from starlette.websockets import WebSocket
from starlette.staticfiles import StaticFiles

from crow_ide.api.files import (
    list_files_sync,
    file_details_sync,
    create_file_sync,
    update_file_sync,
    delete_file_sync,
)
from crow_ide.api.terminal import TerminalHandler
from crow_ide.acp_bridge import ACPBridge


async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


async def list_files(request: Request) -> JSONResponse:
    """List files in a directory."""
    data = await request.json()
    path = data.get("path", os.environ.get("CROW_WORKSPACE", "."))
    relative_path = data.get("relative_path")

    try:
        result = list_files_sync(path, relative_path)
        return JSONResponse(result)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def file_details(request: Request) -> JSONResponse:
    """Get file details and contents."""
    data = await request.json()
    path = data.get("path")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = file_details_sync(path)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def create_file(request: Request) -> JSONResponse:
    """Create a new file."""
    data = await request.json()
    path = data.get("path")
    contents = data.get("contents", "")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = create_file_sync(path, contents)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_file(request: Request) -> JSONResponse:
    """Update file contents."""
    data = await request.json()
    path = data.get("path")
    contents = data.get("contents")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)
    if contents is None:
        return JSONResponse({"error": "contents is required"}, status_code=400)

    try:
        result = update_file_sync(path, contents)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def delete_file(request: Request) -> JSONResponse:
    """Delete a file."""
    data = await request.json()
    path = data.get("path")

    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    try:
        result = delete_file_sync(path)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


async def terminal_websocket(websocket: WebSocket) -> None:
    """Handle terminal WebSocket connections."""
    handler = TerminalHandler()
    await handler.handle(websocket)


async def acp_websocket(websocket: WebSocket) -> None:
    """Handle ACP WebSocket connections."""
    # Default ACP command (can be configured via env)
    # Uses mock_agent.py by default for demo purposes
    default_command = f"python3 {Path(__file__).parent / 'mock_agent.py'}"
    command = os.environ.get("CROW_ACP_COMMAND", default_command).split()
    bridge = ACPBridge(command)
    await bridge.handle(websocket)


# Frontend paths
FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIR / "index.html"


async def index(request: Request) -> FileResponse:
    """Serve the frontend index.html."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return JSONResponse({"error": "Frontend not built. Run: cd crow_ide/frontend && pnpm build"}, status_code=404)


# Define routes
routes = [
    Route("/", index, methods=["GET"]),
    Route("/api/health", health, methods=["GET"]),
    Route("/api/files/list", list_files, methods=["POST"]),
    Route("/api/files/details", file_details, methods=["POST"]),
    Route("/api/files/create", create_file, methods=["POST"]),
    Route("/api/files/update", update_file, methods=["POST"]),
    Route("/api/files/delete", delete_file, methods=["POST"]),
    WebSocketRoute("/terminal", terminal_websocket),
    WebSocketRoute("/acp", acp_websocket),
]

# Add static file serving if frontend is built
if FRONTEND_DIR.exists():
    routes.append(Mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets"))

# Create app
app = Starlette(routes=routes, debug=True)
