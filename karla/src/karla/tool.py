"""Base tool interface and types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from executing a tool."""

    output: str
    is_error: bool = False
    stdout: str | None = None
    stderr: str | None = None

    @classmethod
    def success(
        cls, output: str, stdout: str | None = None, stderr: str | None = None
    ) -> "ToolResult":
        return cls(output=output, is_error=False, stdout=stdout, stderr=stderr)

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        return cls(output=message, is_error=True)


@dataclass
class ToolDefinition:
    """OpenAI-compatible tool definition."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_openai_schema(self, strict: bool = True) -> dict[str, Any]:
        """Convert to OpenAI function calling schema.

        Args:
            strict: If True, adds strict mode for llama.cpp compatibility.
                    This puts ALL parameters in 'required' and sets additionalProperties=false.
        """
        params = dict(self.parameters)

        if strict:
            # For strict mode (required for llama.cpp grammar parsing):
            # 1. All parameters must be in 'required' array
            # 2. additionalProperties must be false
            properties = params.get("properties", {})
            params["required"] = list(properties.keys())
            params["additionalProperties"] = False

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
                "strict": strict,
            },
        }


@dataclass
class ToolContext:
    """Context passed to tool execution."""

    working_dir: str
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled


class Tool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used for invocation."""
        ...

    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's schema definition."""
        ...

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Execute the tool with given arguments."""
        ...

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        """Optional: human-readable summary of execution for logs/display."""
        return None

    def to_letta_source(self, strict: bool = True) -> str:
        """Generate Python source code for Letta tool registration.

        Tools are registered with Letta as stubs that raise exceptions,
        since actual execution happens client-side.

        Args:
            strict: If True, generates strict-mode compatible signatures.
                    All parameters are required (no defaults) for llama.cpp grammar.
        """
        defn = self.definition()

        # Build function signature from parameters
        params = defn.parameters.get("properties", {})
        required = set(defn.parameters.get("required", []))

        sig_parts = []
        for param_name, param_info in params.items():
            param_type = _json_type_to_python(param_info.get("type", "str"))

            if strict:
                # In strict mode, ALL params are required (no defaults).
                # This is required for llama.cpp grammar parsing.
                sig_parts.append(f"{param_name}: {param_type}")
            else:
                # Non-strict mode - optional params have defaults
                if param_name in required:
                    sig_parts.append(f"{param_name}: {param_type}")
                else:
                    default = _get_default_value(param_info)
                    sig_parts.append(f"{param_name}: {param_type} = {default}")

        signature = ", ".join(sig_parts)

        # Build docstring - Letta parses Args section for parameter descriptions
        # Format must match Lares: Args: at column 0 relative to docstring content
        docstring_lines = [defn.description]
        if params:
            docstring_lines.append("")
            docstring_lines.append("Args:")
            for param_name, param_info in params.items():
                param_desc = param_info.get("description", "No description")
                # Ensure description is not empty (Letta requires it)
                if not param_desc.strip():
                    param_desc = f"The {param_name} parameter"
                docstring_lines.append(f"    {param_name}: {param_desc}")

        docstring_lines.append("")
        docstring_lines.append("Returns:")
        docstring_lines.append("    Tool execution result")

        docstring = "\n".join(docstring_lines)

        return f'''def {defn.name}({signature}) -> str:
    """
    {docstring}
    """
    raise Exception("Client-side tool")
'''


def _json_type_to_python(json_type: str) -> str:
    """Convert JSON schema type to Python type hint."""
    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
    }
    return type_map.get(json_type, "str")


def _get_default_value(param_info: dict[str, Any]) -> str:
    """Get default value for optional parameter."""
    if "default" in param_info:
        default = param_info["default"]
        if isinstance(default, str):
            return f'"{default}"'
        return repr(default)

    json_type = param_info.get("type", "string")
    defaults = {
        "string": "None",
        "integer": "None",
        "number": "None",
        "boolean": "False",
        "array": "None",
        "object": "None",
    }
    return defaults.get(json_type, "None")
