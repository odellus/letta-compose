"""Karla tools - coding tools for file operations, search, and shell execution."""

from karla.tools.ask_user import AskUserQuestionTool
from karla.tools.bash import BashTool
from karla.tools.bash_background import BashOutputTool, KillBashTool
from karla.tools.edit import EditTool
from karla.tools.glob import GlobTool
from karla.tools.grep import GrepTool
from karla.tools.plan_mode import EnterPlanModeTool, ExitPlanModeTool
from karla.tools.read import ReadTool
from karla.tools.skill import SkillTool
from karla.tools.task import TaskOutputTool, TaskTool
from karla.tools.todo import TodoStore, TodoWriteTool
from karla.tools.web_fetch import WebFetchTool
from karla.tools.web_search import WebSearchTool
from karla.tools.write import WriteTool

__all__ = [
    # File tools
    "ReadTool",
    "WriteTool",
    "EditTool",
    # Shell tools
    "BashTool",
    "BashOutputTool",
    "KillBashTool",
    # Search tools
    "GrepTool",
    "GlobTool",
    # Web tools
    "WebSearchTool",
    "WebFetchTool",
    # Planning tools
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    "TodoWriteTool",
    "TodoStore",
    # Agent tools
    "TaskTool",
    "TaskOutputTool",
    "SkillTool",
    "AskUserQuestionTool",
    # Factory
    "create_default_registry",
]


def create_default_registry(working_dir: str, skills_dir: str | None = None):
    """Create a registry with all default tools.

    Args:
        working_dir: Working directory for file operations
        skills_dir: Optional directory containing skills

    Returns:
        ToolRegistry with all tools registered
    """
    from karla.registry import ToolRegistry

    registry = ToolRegistry()

    # File tools
    registry.register(ReadTool(working_dir))
    registry.register(WriteTool(working_dir))
    registry.register(EditTool(working_dir))

    # Shell tools
    registry.register(BashTool())
    registry.register(BashOutputTool())
    registry.register(KillBashTool())

    # Search tools
    registry.register(GrepTool(working_dir))
    registry.register(GlobTool(working_dir))

    # Web tools
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())

    # Planning tools
    registry.register(EnterPlanModeTool())
    registry.register(ExitPlanModeTool())
    registry.register(TodoWriteTool())

    # Agent tools
    task_tool = TaskTool()
    registry.register(task_tool)
    registry.register(TaskOutputTool(task_tool))
    registry.register(SkillTool(skills_dir))
    registry.register(AskUserQuestionTool())

    return registry
