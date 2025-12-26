"""AskUserQuestion tool - pauses execution to ask the user a question."""

from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult


class AskUserQuestionTool(Tool):
    """Ask the user a question and wait for response."""

    @property
    def name(self) -> str:
        return "AskUserQuestion"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="AskUserQuestion",
            description="""Pauses execution to ask the user a question.

Use this tool when you need clarification or user input to proceed.
The agent will pause until the user responds.

Guidelines:
- Ask clear, specific questions
- Use when you genuinely need user input to make a decision
- Don't ask rhetorical questions
- Prefer making reasonable assumptions when possible""",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user",
                    },
                },
                "required": ["question"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        question = args.get("question")
        if not question:
            return ToolResult.error("question is required")

        # This tool is special - it signals to the runtime that user input is needed
        # The actual user interaction is handled by the caller (CLI, ACP, etc.)
        return ToolResult.success(f"[AWAITING_USER_INPUT]\n{question}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        question = args.get("question", "")
        return f"ask: {question[:50]}{'...' if len(question) > 50 else ''}"
