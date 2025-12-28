"""Prompt-based slash commands: /remember, /init."""

import os
import subprocess
from karla.commands.registry import register, CommandType
from karla.commands.context import CommandContext


REMEMBER_PROMPT = """# Memory Request

The user has invoked the `/remember` command, which indicates they want you to commit something to memory.

## What This Means

The user wants you to use your memory tools to remember information from the conversation. This could be:

- **A correction**: "You need to run the linter BEFORE committing" -> they want you to remember this workflow
- **A preference**: "I prefer tabs over spaces" -> store in the appropriate memory block
- **A fact**: "The API key is stored in .env.local" -> project-specific knowledge
- **A rule**: "Never push directly to main" -> behavioral guideline

## Your Task

1. **Identify what to remember**: Look at the recent conversation context. What did the user say that they want you to remember? If they provided text after `/remember`, that's what they want remembered.

2. **Determine the right memory block**: Use your memory tools to store the information in the appropriate block.

3. **Confirm the update**: After updating memory, briefly confirm what you remembered and where you stored it.

## Guidelines

- Be concise - distill the information to its essence
- Avoid duplicates - check if similar information already exists
- Match existing formatting of memory blocks
- If unclear what to remember, ask the user to clarify
"""


def gather_git_context(working_dir: str) -> str:
    """Gather git context for /init command."""
    try:
        # Check if we're in a git repo
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=working_dir,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Not in a git repository."

    def run_git(cmd: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip()
        except Exception as e:
            return f"(error: {e})"

    branch = run_git(["branch", "--show-current"])
    status = run_git(["status", "--short"])
    recent_commits = run_git(["log", "--oneline", "-10"])

    # Try to get main branch
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
        )
        main_branch = result.stdout.strip().replace("refs/remotes/origin/", "")
    except Exception:
        main_branch = "main"

    return f"""## Current Project Context

**Working directory**: {working_dir}

### Git Status
- **Current branch**: {branch}
- **Main branch**: {main_branch}
- **Status**:
{status or "(clean working tree)"}

### Recent Commits
{recent_commits}
"""


INIT_PROMPT_TEMPLATE = """The user has requested memory initialization via /init.

## 1. Load the initializing-memory skill

First, check your `loaded_skills` memory block. If the `initializing-memory` skill is not already loaded:
1. Use the `Skill` tool with `command: "load", skills: ["initializing-memory"]`
2. The skill contains comprehensive instructions for memory initialization

If the skill fails to load, proceed with your best judgment based on these guidelines:
- Ask upfront questions (research depth, identity, related repos, workflow style)
- Research the project based on chosen depth
- Create/update memory blocks with project info, user preferences, conventions

{git_context}
"""


@register("/remember", "Remember something from conversation", CommandType.PROMPT, order=13)
async def cmd_remember(ctx: CommandContext, args: str = "") -> str:
    """Tell agent to remember something."""
    if args:
        message = f"<system-reminder>\n{REMEMBER_PROMPT}\n</system-reminder>\n\n{args}"
    else:
        message = f"<system-reminder>\n{REMEMBER_PROMPT}\n\nLook at recent conversation to identify what to remember.\n</system-reminder>"

    ctx.inject_prompt = message
    return "Processing memory request..."


@register("/init", "Initialize agent memory from project", CommandType.PROMPT, order=14)
async def cmd_init(ctx: CommandContext, args: str = "") -> str:
    """Initialize or re-initialize agent memory."""
    git_context = gather_git_context(ctx.working_dir)
    init_message = f"<system-reminder>\n{INIT_PROMPT_TEMPLATE.format(git_context=git_context)}\n</system-reminder>"

    ctx.inject_prompt = init_message
    return "Initializing memory..."
