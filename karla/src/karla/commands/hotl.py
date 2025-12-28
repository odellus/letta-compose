"""HOTL (Human Out of The Loop) commands.

Commands for starting and managing HOTL loops.
"""

import re
from karla.commands.context import CommandContext
from karla.commands.registry import register, CommandType
from karla.hotl import HOTLLoop


def parse_hotl_args(args: str) -> tuple[str, int, str | None]:
    """Parse /hotl command arguments.

    Format: <prompt> [--max-iterations N] [--completion-promise TEXT]

    Returns:
        Tuple of (prompt, max_iterations, completion_promise)
    """
    max_iterations = 0
    completion_promise = None

    # Extract --max-iterations
    match = re.search(r'--max-iterations\s+(\d+)', args)
    if match:
        max_iterations = int(match.group(1))
        args = args[:match.start()] + args[match.end():]

    # Extract --completion-promise (quoted or unquoted)
    match = re.search(r'--completion-promise\s+"([^"]+)"', args)
    if match:
        completion_promise = match.group(1)
        args = args[:match.start()] + args[match.end():]
    else:
        match = re.search(r'--completion-promise\s+(\S+)', args)
        if match:
            completion_promise = match.group(1)
            args = args[:match.start()] + args[match.end():]

    # Remaining text is the prompt (strip quotes if wrapped)
    prompt = args.strip()
    if prompt.startswith('"') and prompt.endswith('"'):
        prompt = prompt[1:-1]

    return prompt, max_iterations, completion_promise


@register("/hotl", "Start HOTL loop (/hotl <prompt> [--max-iterations N] [--completion-promise TEXT])", CommandType.CLI, order=20)
async def cmd_hotl(ctx: CommandContext, args: str = "") -> str:
    """Start a HOTL (Human Out of The Loop) loop.

    Usage:
        /hotl "Your task prompt" --max-iterations 20 --completion-promise "DONE"

    The loop will:
    1. Send your prompt to the agent
    2. Agent works on the task
    3. When done, same prompt is sent again
    4. Agent sees its previous work in files
    5. Continues until completion promise or max iterations
    """
    if not args.strip():
        return """Usage: /hotl <prompt> [--max-iterations N] [--completion-promise TEXT]

Examples:
  /hotl "Fix the failing tests" --max-iterations 10
  /hotl "Implement feature X" --completion-promise "COMPLETE"
  /hotl "Refactor the auth module" --max-iterations 20 --completion-promise "DONE"

Options:
  --max-iterations N       Stop after N iterations (default: unlimited)
  --completion-promise T   Stop when agent outputs <promise>T</promise>"""

    prompt, max_iterations, completion_promise = parse_hotl_args(args)

    if not prompt:
        return "Error: No prompt provided. Usage: /hotl <prompt>"

    loop = HOTLLoop(ctx.working_dir)

    # Check if already running
    if loop.is_active():
        state = loop.get_state()
        return f"HOTL loop already active (iteration {state.iteration}). Use /cancel-hotl first."

    # Start the loop
    state = loop.start(
        prompt=prompt,
        max_iterations=max_iterations,
        completion_promise=completion_promise,
    )

    # Build status message
    status_parts = ["HOTL loop started"]
    if max_iterations > 0:
        status_parts.append(f"max {max_iterations} iterations")
    if completion_promise:
        status_parts.append(f"promise: <promise>{completion_promise}</promise>")

    status = " | ".join(status_parts)

    # Set the prompt to be injected
    ctx.inject_prompt = (
        f"<system-reminder>\n"
        f"{status}\n"
        f"</system-reminder>\n\n"
        f"{prompt}"
    )

    return status


@register("/cancel-hotl", "Cancel active HOTL loop", CommandType.CLI, order=21)
async def cmd_cancel_hotl(ctx: CommandContext) -> str:
    """Cancel the active HOTL loop."""
    loop = HOTLLoop(ctx.working_dir)
    was_active, iteration = loop.cancel()

    if was_active:
        return f"HOTL loop cancelled (was at iteration {iteration})"
    else:
        return "No active HOTL loop"


@register("/hotl-status", "Show HOTL loop status", CommandType.CLI, order=22)
async def cmd_hotl_status(ctx: CommandContext) -> str:
    """Show status of active HOTL loop."""
    loop = HOTLLoop(ctx.working_dir)
    state = loop.get_state()

    if not state:
        return "No active HOTL loop"

    lines = [
        f"HOTL Loop Status",
        f"  Iteration: {state.iteration}" + (f"/{state.max_iterations}" if state.max_iterations > 0 else ""),
        f"  Max iterations: {state.max_iterations or 'unlimited'}",
        f"  Completion promise: {state.completion_promise or 'none'}",
        f"",
        f"Prompt:",
        f"  {state.prompt[:100]}{'...' if len(state.prompt) > 100 else ''}",
    ]

    return "\n".join(lines)


@register("/hotl-help", "Explain HOTL mode", CommandType.CLI, order=23, hidden=True)
async def cmd_hotl_help(ctx: CommandContext) -> str:
    """Show HOTL mode help."""
    return """HOTL (Human Out of The Loop) Mode

HOTL mode creates iterative, self-referential agent loops where:
1. The agent receives a prompt
2. Works on the task, modifying files
3. Attempts to complete
4. If not done, receives the SAME prompt again
5. Sees its previous work in files
6. Iterates until completion criteria met

Commands:
  /hotl <prompt> [options]   Start a HOTL loop
  /cancel-hotl               Cancel active loop
  /hotl-status               Show loop status

Options for /hotl:
  --max-iterations N         Stop after N iterations
  --completion-promise TEXT  Stop when <promise>TEXT</promise> appears

Example:
  /hotl "Fix all failing tests" --max-iterations 20 --completion-promise "ALL TESTS PASS"

The agent will iterate, running tests and fixing issues, until either:
- It outputs <promise>ALL TESTS PASS</promise>
- 20 iterations are reached

Best Practices:
- Always set --max-iterations as a safety net
- Use clear, verifiable completion promises
- Write prompts with incremental goals
- Include self-correction instructions in prompts

Learn more: https://ghuntley.com/ralph/"""
