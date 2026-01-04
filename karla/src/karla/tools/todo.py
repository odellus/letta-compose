"""TodoWrite tool - manages a structured task list."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult


class TodoStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TodoItem:
    content: str
    status: TodoStatus
    active_form: str  # Present continuous form (e.g., "Running tests")


@dataclass
class TodoStore:
    """Shared todo state across tools and sessions."""

    items: list[TodoItem] = field(default_factory=list)

    def to_list(self) -> list[dict[str, str]]:
        return [
            {
                "content": item.content,
                "status": item.status.value,
                "activeForm": item.active_form,
            }
            for item in self.items
        ]

    def from_list(self, todos: list[dict[str, Any]]) -> None:
        self.items = []
        for todo in todos:
            status_str = todo.get("status", "pending")
            try:
                status = TodoStatus(status_str)
            except ValueError:
                status = TodoStatus.PENDING

            self.items.append(
                TodoItem(
                    content=todo.get("content", ""),
                    status=status,
                    active_form=todo.get("activeForm", todo.get("content", "")),
                )
            )


# Global todo store (can be replaced with session-specific stores)
_todo_store = TodoStore()


def get_todo_store() -> TodoStore:
    return _todo_store


def set_todo_store(store: TodoStore) -> None:
    global _todo_store
    _todo_store = store


class TodoWriteTool(Tool):
    """Manage a structured task list."""

    def __init__(self, store: TodoStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> TodoStore:
        return self._store if self._store else get_todo_store()

    @property
    def name(self) -> str:
        return "TodoWrite"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="TodoWrite",
            description="""Create and manage a structured task list for tracking progress.

Use this to:
- Plan complex multi-step tasks (3+ steps)
- Track progress on user requests
- Break down large tasks into smaller steps
- Show the user your progress

Guidelines:
- Mark tasks as in_progress BEFORE starting work
- Mark tasks as completed IMMEDIATELY after finishing
- Only have ONE task in_progress at a time
- Provide both content (imperative) and activeForm (present continuous)

Task states:
- pending: Not yet started
- in_progress: Currently working on
- completed: Finished successfully

Do NOT use for trivial single-step tasks.""",
            parameters={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "The complete updated todo list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "Task description (imperative, e.g., 'Run tests')",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "Task status",
                                },
                                "activeForm": {
                                    "type": "string",
                                    "description": "Present continuous form (e.g., 'Running tests')",
                                },
                            },
                            "required": ["content", "status", "activeForm"],
                        },
                    },
                },
                "required": ["todos"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        todos = args.get("todos")
        if todos is None:
            return ToolResult.error("todos is required")

        if not isinstance(todos, list):
            return ToolResult.error("todos must be an array")

        # Update the store
        self.store.from_list(todos)

        # Count statuses
        pending = sum(1 for t in self.store.items if t.status == TodoStatus.PENDING)
        in_progress = sum(1 for t in self.store.items if t.status == TodoStatus.IN_PROGRESS)
        completed = sum(1 for t in self.store.items if t.status == TodoStatus.COMPLETED)

        return ToolResult.success(
            f"Updated todo list: {completed} completed, {in_progress} in progress, {pending} pending"
        )

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        todos = args.get("todos", [])
        in_progress = [t for t in todos if t.get("status") == "in_progress"]
        if in_progress:
            return f"todo: {in_progress[0].get('activeForm', 'working')}"
        return "todo: updated"


class TodoReadTool(Tool):
    """Read the current todo list state."""

    def __init__(self, store: TodoStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> TodoStore:
        return self._store if self._store else get_todo_store()

    @property
    def name(self) -> str:
        return "TodoRead"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="TodoRead",
            description="""Read the current todo list to see your tracked tasks.

Use this when:
- You need to check your current task list after context compaction
- You want to verify the state of your todos
- You're resuming work and need to know what tasks are pending

Returns the full todo list with content, status, and activeForm for each item.""",
            parameters={
                "type": "object",
                "properties": {},
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        todos = self.store.to_list()

        if not todos:
            return ToolResult.success("No todos in the list. Use TodoWrite to create tasks.")

        # Format nicely for the agent
        import json
        return ToolResult.success(json.dumps(todos, indent=2))

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        count = len(self.store.items)
        return f"todo: read {count} items"
