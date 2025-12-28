"""WebFetch tool - fetch and convert web pages to markdown."""

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Maximum content size to fetch (5MB)
MAX_CONTENT_SIZE = 5 * 1024 * 1024

# Maximum output length
MAX_OUTPUT_LENGTH = 50000


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using html2text."""
    try:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines
        h.unicode_snob = True
        h.skip_internal_links = True
        h.inline_links = True
        h.protect_links = True

        return h.handle(html)
    except ImportError:
        # Fallback: basic tag stripping
        import re

        # Remove script and style tags
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class WebFetchTool(Tool):
    """Fetch a web page and convert to markdown."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "WebFetch"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="WebFetch",
            description="""Fetch a web page and convert its content to markdown.

Use this to:
- Read documentation pages
- Fetch README files from GitHub
- Get content from blog posts or articles
- Read API documentation

The content is converted from HTML to markdown for easier reading.
Large pages are truncated to avoid context overflow.""",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                    "selector": {
                        "type": "string",
                        "description": "Optional CSS selector to extract specific content (e.g., 'article', 'main', '.content')",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = args.get("url")
        if not url:
            return ToolResult.error("url is required")

        selector = args.get("selector")

        # Validate URL
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ToolResult.error("URL must use http or https")
        except Exception:
            return ToolResult.error(f"Invalid URL: {url}")

        # Fetch the page
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Karla/1.0; +https://github.com/letta-ai/karla)"
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ToolResult.error(
                        f"Unsupported content type: {content_type}. "
                        "WebFetch only supports HTML and plain text."
                    )

                # Check size
                content_length = len(response.content)
                if content_length > MAX_CONTENT_SIZE:
                    return ToolResult.error(
                        f"Content too large: {content_length / 1024 / 1024:.1f}MB "
                        f"(max {MAX_CONTENT_SIZE / 1024 / 1024:.0f}MB)"
                    )

                html = response.text

        except httpx.ConnectError:
            return ToolResult.error(f"Could not connect to {parsed.netloc}")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"HTTP {e.response.status_code}: {url}")
        except httpx.TimeoutException:
            return ToolResult.error(f"Timeout fetching {url}")
        except Exception as e:
            logger.exception("WebFetch failed")
            return ToolResult.error(f"Fetch failed: {e}")

        # Extract content with selector if provided
        if selector:
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html, "html.parser")
                element = soup.select_one(selector)
                if element:
                    html = str(element)
                else:
                    return ToolResult.error(f"Selector '{selector}' not found on page")
            except ImportError:
                logger.warning("BeautifulSoup not available, ignoring selector")
            except Exception as e:
                logger.warning(f"Selector failed: {e}")

        # Convert to markdown
        markdown = html_to_markdown(html)

        # Truncate if too long
        if len(markdown) > MAX_OUTPUT_LENGTH:
            markdown = markdown[:MAX_OUTPUT_LENGTH] + "\n\n... (truncated)"

        # Add source header
        output = f"# Content from {url}\n\n{markdown}"

        return ToolResult.success(output)

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        url = args.get("url", "")
        try:
            parsed = urlparse(url)
            return f"fetch: {parsed.netloc}{parsed.path[:30]}"
        except Exception:
            return f"fetch: {url[:50]}"
