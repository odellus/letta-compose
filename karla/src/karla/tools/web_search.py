"""WebSearch tool - search the internet via SearXNG."""

import os
import logging
from typing import Any

import httpx

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Default SearXNG URL
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8082")


class WebSearchTool(Tool):
    """Search the internet using SearXNG."""

    def __init__(self, searxng_url: str | None = None) -> None:
        self._searxng_url = searxng_url or SEARXNG_URL

    @property
    def name(self) -> str:
        return "WebSearch"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="WebSearch",
            description="""Search the internet for information.

Uses SearXNG to search multiple search engines and return results.
Returns titles, URLs, and content snippets for each result.

Use this for:
- Finding documentation and tutorials
- Researching libraries and tools
- Getting current information beyond training data
- Finding solutions to specific problems""",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5, max: 20)",
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = args.get("query")
        if not query:
            return ToolResult.error("query is required")

        limit = min(args.get("limit", 5), 20)

        try:
            async with httpx.AsyncClient(base_url=self._searxng_url, timeout=30.0) as client:
                response = await client.get(
                    "/search",
                    params={"q": query, "format": "json"},
                )
                response.raise_for_status()
                data = response.json()

        except httpx.ConnectError:
            return ToolResult.error(
                f"Could not connect to SearXNG at {self._searxng_url}. "
                "Make sure SearXNG is running."
            )
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Search failed: {e.response.status_code}")
        except Exception as e:
            logger.exception("WebSearch failed")
            return ToolResult.error(f"Search failed: {e}")

        # Format results
        lines = []

        # Include infoboxes if present
        for infobox in data.get("infoboxes", []):
            lines.append(f"## {infobox.get('infobox', 'Info')}")
            if infobox.get("content"):
                lines.append(infobox["content"])
            lines.append("")

        # Include search results
        results = data.get("results", [])
        if not results:
            lines.append("No results found.")
        else:
            for i, result in enumerate(results[:limit]):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                content = result.get("content", "")

                lines.append(f"### {i+1}. {title}")
                lines.append(f"URL: {url}")
                if content:
                    lines.append(content)
                lines.append("")

        return ToolResult.success("\n".join(lines))

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        query = args.get("query", "")
        return f"web search: {query[:50]}"
