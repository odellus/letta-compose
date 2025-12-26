"""Plan mode tools - EnterPlanMode and ExitPlanMode."""

from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult


class EnterPlanModeTool(Tool):
    """Enter planning mode for complex tasks."""

    @property
    def name(self) -> str:
        return "EnterPlanMode"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="EnterPlanMode",
            description="""Enter planning mode to design an implementation approach before coding.

Use this proactively when starting non-trivial implementation tasks.
In plan mode, you explore the codebase and design an approach for user approval.

When to use:
- New feature implementation
- Multiple valid approaches exist
- Code modifications affecting existing behavior
- Architectural decisions
- Multi-file changes
- Unclear requirements needing exploration

When NOT to use:
- Single-line fixes, typos, small tweaks
- Tasks with very specific, detailed instructions
- Pure research/exploration tasks""",
            parameters={
                "type": "object",
                "properties": {},
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # This signals to the runtime to enter plan mode
        return ToolResult.success("[ENTERING_PLAN_MODE]")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        return "entering plan mode"


class ExitPlanModeTool(Tool):
    """Exit planning mode after plan is ready."""

    @property
    def name(self) -> str:
        return "ExitPlanMode"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ExitPlanMode",
            description="""Exit planning mode when the plan is ready for user approval.

Use this after you have:
1. Explored the codebase
2. Written your plan to the plan file
3. Are ready for user to review and approve

Only use this for implementation planning, not for research tasks.""",
            parameters={
                "type": "object",
                "properties": {},
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # This signals to the runtime to exit plan mode
        return ToolResult.success("[EXITING_PLAN_MODE]")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        return "exiting plan mode"
