"""Bash tool - executes shell commands."""

import asyncio
import os
import shlex
from typing import Any

from karla.tool import Tool, ToolContext, ToolDefinition, ToolResult

DEFAULT_TIMEOUT = 120  # seconds
MAX_OUTPUT_SIZE = 100_000  # characters


class BashTool(Tool):
    """Execute bash commands."""

    def __init__(self, shell: str = "/bin/bash") -> None:
        self.shell = shell

    @property
    def name(self) -> str:
        return "Bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Bash",
            description="""Executes a bash command in the shell.

IMPORTANT: This tool is for terminal operations like git, npm, docker, etc.
DO NOT use it for file operations - use the specialized tools instead:
- File search: Use Glob (NOT find or ls)
- Content search: Use Grep (NOT grep or rg)
- Read files: Use Read (NOT cat/head/tail)
- Edit files: Use Edit (NOT sed/awk)
- Write files: Use Write (NOT echo >/cat <<EOF)

Usage:
- Commands run in the current working directory
- Provide a clear description of what the command does
- For long-running commands, consider using timeout parameter
- Output is captured from both stdout and stderr
- Always quote file paths containing spaces with double quotes

# Committing changes with git

Only create commits when requested by the user. When creating commits:

1. Run git status and git diff to see all changes
2. Analyze changes and draft a commit message that:
   - Summarizes the nature of changes (new feature, bug fix, refactor, etc.)
   - Focuses on the "why" rather than the "what"
   - Is concise (1-2 sentences)
3. Run git add for relevant files
4. Create the commit with message ending with:
   🤖 Generated with Karla
   Co-Authored-By: Karla <noreply@letta.com>

IMPORTANT commit format - use HEREDOC for proper formatting:
```
git commit -m "$(cat <<'EOF'
Commit message here.

🤖 Generated with Karla

Co-Authored-By: Karla <noreply@letta.com>
EOF
)"
```

Git Safety:
- NEVER use git push --force, hard reset, or other destructive commands
- NEVER skip hooks (--no-verify) unless explicitly requested
- NEVER use interactive flags (-i) as they're not supported
- NEVER commit .env, credentials, or secret files

# Creating pull requests

When asked to create a pull request:

1. Run git status and git diff to understand all changes
2. Check if the current branch tracks a remote and if it needs pushing
3. Run git log to see commit history for the branch
4. Create PR using gh pr create with format:

```
gh pr create --title "PR title" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points summarizing changes>

## Test plan
[How to test the changes]

🤖 Generated with Karla
EOF
)"
```

Important PR notes:
- Return the PR URL when done
- Use --base to specify target branch if not main/master
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` to view PR comments""",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this command does (5-10 words)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120, max 120)",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = args.get("command")
        if not command:
            return ToolResult.error("command is required")

        timeout = min(args.get("timeout", DEFAULT_TIMEOUT), DEFAULT_TIMEOUT)

        if ctx.is_cancelled():
            return ToolResult.error("Cancelled")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ctx.working_dir,
                shell=True,
                env={**os.environ, "TERM": "dumb"},  # Disable color codes
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.error(f"Command timed out after {timeout} seconds")

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate if too large
            if len(stdout_str) > MAX_OUTPUT_SIZE:
                stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + "\n... [output truncated]"
            if len(stderr_str) > MAX_OUTPUT_SIZE:
                stderr_str = stderr_str[:MAX_OUTPUT_SIZE] + "\n... [stderr truncated]"

            # Build output
            output_parts = []
            if stdout_str.strip():
                output_parts.append(stdout_str.rstrip())
            if stderr_str.strip():
                output_parts.append(f"[stderr]\n{stderr_str.rstrip()}")
            if process.returncode != 0:
                output_parts.append(f"[exit code: {process.returncode}]")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            return ToolResult(
                output=output,
                is_error=process.returncode != 0,
                stdout=stdout_str if stdout_str.strip() else None,
                stderr=stderr_str if stderr_str.strip() else None,
            )

        except Exception as e:
            return ToolResult.error(f"Failed to execute command: {e}")

    def humanize(self, args: dict[str, Any], result: ToolResult) -> str | None:
        command = args.get("command", "command")
        # Truncate long commands
        if len(command) > 60:
            command = command[:57] + "..."

        if result.is_error:
            return f"$ {command} -> error"
        return f"$ {command} -> ok"
