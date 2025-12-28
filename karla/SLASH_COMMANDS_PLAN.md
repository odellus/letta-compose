# Karla Slash Commands Implementation Plan

## Overview

This document outlines the plan for implementing slash commands in Karla, based on letta-code's implementation.

## Reference Files (letta-code)

| File | Purpose |
|------|---------|
| `src/cli/commands/registry.ts` | Command registry with handlers |
| `src/cli/App.tsx` | Main app handling command execution |
| `src/cli/commands/profile.ts` | Profile/pin/unpin command implementations |
| `src/agent/prompts/remember.md` | Remember command prompt template |
| `src/skills/builtin/init/SKILL.md` | Init command skill (loaded by /init) |

## Architecture

### Letta-code Approach
1. **Registry Pattern**: Commands defined in `registry.ts` with `desc`, `handler`, `hidden`, `order`
2. **Special Handling**: Most commands just return placeholder text - actual logic is in `App.tsx`
3. **Three command types**:
   - **API Commands**: Call Letta API directly (e.g., `/clear` → `messages.reset()`)
   - **Prompt Commands**: Inject special prompts to agent (e.g., `/remember`, `/init`)
   - **UI Commands**: Open selectors/dialogs (e.g., `/agents`, `/memory`)

### Karla Approach
Since Karla is CLI-only (no TUI yet), we'll focus on:
1. **API Commands**: Direct API calls
2. **Prompt Commands**: Inject prompts and continue conversation
3. **CLI Commands**: Print information or modify state

## Command Categories

### Phase 1: Essential Commands (Priority: HIGH)

These are needed for basic operation:

| Command | Type | Implementation |
|---------|------|----------------|
| `/clear` | API | `client.agents.messages.reset(agent_id)` |
| `/compact` | API | `client.agents.messages.compact(agent_id)` |
| `/remember [text]` | Prompt | Send remember prompt to agent |
| `/init` | Prompt | Send init prompt + load skill |
| `/memory` | CLI | Print current memory blocks |
| `/help` | CLI | List available commands |

### Phase 2: Agent Management (Priority: MEDIUM)

| Command | Type | Implementation |
|---------|------|----------------|
| `/new` | API | Create new agent, switch to it |
| `/agents` | CLI | List all agents |
| `/rename <name>` | API | `client.agents.modify(agent_id, name=name)` |
| `/pin [-l]` | Settings | Save agent to global/local settings |
| `/unpin [-l]` | Settings | Remove agent from settings |
| `/pinned` | CLI | List pinned agents |

### Phase 3: Configuration (Priority: MEDIUM)

| Command | Type | Implementation |
|---------|------|----------------|
| `/model <id>` | API | Update agent's LLM config |
| `/toolset <name>` | API | Switch tool configuration |
| `/system <id>` | API | Update system prompt |

### Phase 4: Advanced (Priority: LOW)

| Command | Type | Implementation |
|---------|------|----------------|
| `/skill [desc]` | Prompt | Enter skill creation mode |
| `/search <query>` | API | Search messages across agents |
| `/usage` | API | Show token usage stats |
| `/bg` | CLI | Show background processes |
| `/exit` | CLI | Exit interactive mode |

## Implementation Details

### 1. Command Registry

```python
# src/karla/commands/registry.py

from dataclasses import dataclass
from typing import Callable, Optional
from enum import Enum

class CommandType(Enum):
    API = "api"      # Calls Letta API
    PROMPT = "prompt"  # Sends prompt to agent
    CLI = "cli"       # Local CLI action

@dataclass
class Command:
    name: str
    description: str
    handler: Callable
    command_type: CommandType
    hidden: bool = False
    order: int = 100

# Registry
COMMANDS: dict[str, Command] = {}

def register(name: str, desc: str, cmd_type: CommandType, order: int = 100, hidden: bool = False):
    """Decorator to register a command."""
    def decorator(func):
        COMMANDS[name] = Command(
            name=name,
            description=desc,
            handler=func,
            command_type=cmd_type,
            hidden=hidden,
            order=order,
        )
        return func
    return decorator
```

### 2. Command Implementations

```python
# src/karla/commands/core.py

from karla.commands.registry import register, CommandType

@register("/clear", "Clear conversation history", CommandType.API, order=10)
async def cmd_clear(ctx: CommandContext) -> str:
    """Reset the agent's message buffer."""
    await ctx.client.agents.messages.reset(
        ctx.agent_id,
        add_default_initial_messages=False,
    )
    return "Conversation cleared. Memory blocks preserved."

@register("/compact", "Summarize conversation history", CommandType.API, order=11)
async def cmd_compact(ctx: CommandContext) -> str:
    """Compact/summarize the conversation."""
    result = await ctx.client.agents.messages.compact(ctx.agent_id)
    return f"Compacted {result.num_messages_before} → {result.num_messages_after} messages"

@register("/memory", "View memory blocks", CommandType.CLI, order=12)
async def cmd_memory(ctx: CommandContext) -> str:
    """Display current memory blocks."""
    agent = await ctx.client.agents.retrieve(ctx.agent_id)
    lines = ["# Memory Blocks", ""]
    for block in agent.memory.blocks:
        lines.append(f"## {block.label}")
        lines.append(block.value[:500] + ("..." if len(block.value) > 500 else ""))
        lines.append("")
    return "\n".join(lines)

@register("/help", "Show available commands", CommandType.CLI, order=100)
async def cmd_help(ctx: CommandContext) -> str:
    """List all available commands."""
    from karla.commands.registry import COMMANDS
    lines = ["# Available Commands", ""]
    for name, cmd in sorted(COMMANDS.items(), key=lambda x: x[1].order):
        if not cmd.hidden:
            lines.append(f"  {name:15} {cmd.description}")
    return "\n".join(lines)
```

### 3. Prompt Commands

```python
# src/karla/commands/prompts.py

from karla.commands.registry import register, CommandType

REMEMBER_PROMPT = """# Memory Request

The user has invoked the `/remember` command...
[Full prompt from letta-code src/agent/prompts/remember.md]
"""

@register("/remember", "Remember something from conversation", CommandType.PROMPT, order=13)
async def cmd_remember(ctx: CommandContext, args: str = "") -> str:
    """Tell agent to remember something."""
    if args:
        message = f"<system-reminder>\n{REMEMBER_PROMPT}\n</system-reminder>{args}"
    else:
        message = f"<system-reminder>\n{REMEMBER_PROMPT}\n\nLook at recent conversation to identify what to remember.\n</system-reminder>"

    # Return the message to be sent to agent
    ctx.inject_prompt = message
    return "Processing memory request..."

@register("/init", "Initialize agent memory", CommandType.PROMPT, order=14)
async def cmd_init(ctx: CommandContext) -> str:
    """Initialize or re-initialize agent memory."""
    # Gather git context
    git_context = gather_git_context()

    init_message = f"""<system-reminder>
The user has requested memory initialization via /init.

## 1. Load the initializing-memory skill

First, check your `loaded_skills` memory block. If the `initializing-memory` skill is not already loaded:
1. Use the `Skill` tool with `command: "load", skills: ["initializing-memory"]`
2. The skill contains comprehensive instructions for memory initialization

{git_context}
</system-reminder>"""

    ctx.inject_prompt = init_message
    return "Initializing memory..."
```

### 4. Command Context

```python
# src/karla/commands/context.py

from dataclasses import dataclass, field
from typing import Optional
from letta_client import Letta

@dataclass
class CommandContext:
    """Context passed to command handlers."""
    client: Letta
    agent_id: str
    working_dir: str
    settings: "SettingsManager"

    # Set by prompt commands to inject a message
    inject_prompt: Optional[str] = None
```

### 5. Command Dispatcher

```python
# src/karla/commands/dispatcher.py

async def dispatch_command(
    input_text: str,
    ctx: CommandContext,
) -> tuple[str, bool]:
    """
    Dispatch a slash command.

    Returns:
        (output, should_continue_to_agent)
    """
    if not input_text.startswith("/"):
        return "", True  # Not a command, send to agent

    parts = input_text.split(maxsplit=1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    if cmd_name not in COMMANDS:
        return f"Unknown command: {cmd_name}. Use /help for available commands.", False

    cmd = COMMANDS[cmd_name]

    try:
        result = await cmd.handler(ctx, args) if cmd.command_type == CommandType.PROMPT else await cmd.handler(ctx)

        # If command injected a prompt, signal to continue
        if ctx.inject_prompt:
            return result, True

        return result, False

    except Exception as e:
        return f"Command failed: {e}", False
```

### 6. Integration with CLI

```python
# src/karla/cli.py (modified)

async def interactive_mode(client, agent_id, executor, settings):
    """Interactive chat mode with slash command support."""
    ctx = CommandContext(
        client=client,
        agent_id=agent_id,
        working_dir=os.getcwd(),
        settings=settings,
    )

    print("Karla Interactive Mode")
    print("Type /help for commands, /exit to quit")
    print()

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            output, continue_to_agent = await dispatch_command(user_input, ctx)
            print(output)

            if user_input == "/exit":
                break

            if continue_to_agent and ctx.inject_prompt:
                # Send injected prompt to agent
                response = await run_agent_loop(
                    client, agent_id, executor, ctx.inject_prompt
                )
                print(f"karla> {response.text}")
                ctx.inject_prompt = None
        else:
            # Regular message to agent
            response = await run_agent_loop(client, agent_id, executor, user_input)
            print(f"karla> {response.text}")
```

## File Structure

```
src/karla/
├── commands/
│   ├── __init__.py
│   ├── registry.py      # Command registration
│   ├── context.py       # CommandContext class
│   ├── dispatcher.py    # Command dispatch logic
│   ├── core.py          # /clear, /compact, /memory, /help
│   ├── prompts.py       # /remember, /init, /skill
│   ├── agents.py        # /new, /agents, /rename, /pin
│   └── config.py        # /model, /toolset, /system
├── prompts/
│   ├── remember.md      # Remember command template
│   └── init.md          # Init command template
└── cli.py               # Updated with interactive mode
```

## API Endpoints Used

| Command | Endpoint |
|---------|----------|
| `/clear` | `POST /v1/agents/{id}/reset-messages` |
| `/compact` | `POST /v1/agents/{id}/messages/compact` |
| `/memory` | `GET /v1/agents/{id}` (includes memory blocks) |
| `/new` | `POST /v1/agents/` |
| `/agents` | `GET /v1/agents/` |
| `/rename` | `PATCH /v1/agents/{id}` |
| `/model` | `PATCH /v1/agents/{id}` (llm_config) |
| `/search` | `POST /v1/agents/messages/search` |

## Testing Plan

### Unit Tests
- Command registry registration
- Command parsing and dispatch
- Prompt generation

### Integration Tests
- `/clear` resets messages
- `/compact` reduces message count
- `/memory` returns block contents
- `/remember` updates memory blocks
- `/init` loads skill and initializes

### E2E Tests
- Full interactive session with commands
- Agent continues working after /clear
- Memory persists after /compact

## Implementation Order

1. **Command Infrastructure** (registry, context, dispatcher)
2. **Core Commands** (/clear, /compact, /memory, /help)
3. **Prompt Commands** (/remember, /init)
4. **Interactive CLI Mode**
5. **Agent Management** (/new, /agents, /pin)
6. **Configuration** (/model, /toolset)

## Notes

### kv_cache_friendly Implications
- `/clear` and `/compact` both trigger system prompt re-render
- This is acceptable because user explicitly requested it
- Normal conversation does NOT update system prompt
- Memory tool writes go to DB, appear on next session

### Prompt Injection Pattern
For prompt commands like `/remember` and `/init`:
1. Command builds a `<system-reminder>` wrapped message
2. Message is sent to agent as user message
3. Agent processes it using its tools (memory, Skill, etc.)
4. Response flows back normally

This pattern lets us leverage the agent's capabilities rather than implementing complex logic ourselves.
