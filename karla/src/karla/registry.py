"""Tool registry for managing and looking up tools."""

from typing import Any

from karla.tool import Tool, ToolDefinition


class ToolRegistry:
    """Registry for managing tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_definitions(self) -> list[ToolDefinition]:
        """Get all tool definitions."""
        return [tool.definition() for tool in self._tools.values()]

    def to_openai_tools(self, strict: bool = True) -> list[dict[str, Any]]:
        """Get all tools in OpenAI function calling format.

        Args:
            strict: If True, uses strict mode for llama.cpp compatibility.
                    All parameters will be in 'required' and additionalProperties=false.
        """
        return [tool.definition().to_openai_schema(strict=strict) for tool in self._tools.values()]

    def to_crow_sources(self, strict: bool = True) -> dict[str, str]:
        """Get all tools as Crow-compatible Python source code.

        Args:
            strict: If True, generates strict-mode compatible signatures for llama.cpp.
        """
        return {tool.name: tool.to_crow_source(strict=strict) for tool in self._tools.values()}

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
