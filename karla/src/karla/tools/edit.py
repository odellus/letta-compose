"""Edit file tool - performs exact string replacements."""

from pathlib import Path
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult


class EditTool(Tool):
    """Edit files by replacing exact string matches."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "Edit"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Edit",
            description="""Performs exact string replacements in files.

Usage:
- The file_path parameter must be an absolute path
- You must read the file first before editing
- The old_string must match exactly (including whitespace/indentation)
- The edit will FAIL if old_string is not unique - provide more context to make it unique
- Use replace_all=true to replace all occurrences (useful for renaming)
- Prefer editing existing files over creating new ones""",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to edit",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences (default false)",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        )

    def _resolve_path(self, path: str) -> Path:
        """Resolve and validate a path."""
        requested = Path(path)
        if requested.is_absolute():
            full_path = requested
        else:
            full_path = self.working_dir / requested

        try:
            canonical = full_path.resolve()
        except OSError as e:
            raise ValueError(f"Cannot resolve path: {e}")

        try:
            canonical.relative_to(self.working_dir)
        except ValueError:
            raise ValueError(f"Path is outside working directory: {path}")

        return canonical

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        file_path = args.get("file_path")
        old_string = args.get("old_string")
        new_string = args.get("new_string")
        replace_all = args.get("replace_all", False)

        if not file_path:
            return ToolResult.error("file_path is required")
        if old_string is None:
            return ToolResult.error("old_string is required")
        if new_string is None:
            return ToolResult.error("new_string is required")
        if old_string == new_string:
            return ToolResult.error("old_string and new_string must be different")

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.error(str(e))

        if not path.exists():
            return ToolResult.error(f"File does not exist: {path}")
        if not path.is_file():
            return ToolResult.error(f"Path is a directory: {path}")

        # Read current content
        try:
            content = path.read_text(encoding="utf-8")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except OSError as e:
            return ToolResult.error(f"Failed to read file: {e}")

        # Check for matches
        count = content.count(old_string)
        if count == 0:
            return ToolResult.error(
                f"old_string not found in file. Make sure it matches exactly, "
                f"including whitespace and indentation."
            )

        if count > 1 and not replace_all:
            return ToolResult.error(
                f"old_string appears {count} times in the file. "
                f"Either provide more context to make it unique, or use replace_all=true "
                f"to replace all occurrences."
            )

        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1

        # Write back
        try:
            path.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except OSError as e:
            return ToolResult.error(f"Failed to write file: {e}")

        if replacements == 1:
            return ToolResult.success(f"Successfully edited {path}")
        else:
            return ToolResult.success(f"Successfully made {replacements} replacements in {path}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        path = args.get("file_path", "file")
        if result.is_error:
            return f"edit {path} -> err: {result.output}"
        return f"edit {path} -> ok"
