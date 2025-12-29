# Karla ACP Implementation Plan

This document tracks the work needed to make Karla fully functional as an ACP server for IDE integrations.

## Current State

- ✅ Basic ACP server working (`initialize`, `session/new`, `session/prompt`, `session/cancel`)
- ✅ Token streaming working (text streams token-by-token)
- ✅ Tool call delta accumulation (tool args stream correctly)
- ✅ Rich tool content (diffs, commands, locations) streaming to ACP
- ✅ Cancellation working (executor flag checked in agent loop)
- ✅ kv_cache_friendly=True set from config
- ❌ Commands not working through ACP
- ❌ Cwd/environment not injected into agent context
- ❌ Agent persistence (reuse same agent across sessions)
- ❌ Memory block updates on clear/compact

---

## Priority 1: Commands in ACP

Commands (`/clear`, `/compact`, `/hotl`, `/pin`, etc.) only work in CLI mode. ACP clients can't access them.

### Approach

In `prompt()` method of `acp_server.py`:
1. Check if prompt text starts with `/`
2. Parse command name and args
3. Route to command handler instead of agent loop
4. Return command output as agent message

### Implementation

```python
async def prompt(self, prompt, session_id, **kwargs):
    text = extract_text(prompt)

    # Check for command
    if text.strip().startswith('/'):
        return await self._handle_command(session_id, text)

    # Normal agent loop
    ...

async def _handle_command(self, session_id, text):
    # Parse command
    parts = text.strip().split(maxsplit=1)
    cmd_name = parts[0]  # e.g., "/clear"
    cmd_args = parts[1] if len(parts) > 1 else ""

    # Look up and execute command
    # Return result via session_update
```

### Commands to Support

| Command | Priority | Notes |
|---------|----------|-------|
| `/clear` | High | Clear conversation, refresh memory blocks |
| `/compact` | High | Compact conversation, update memory |
| `/pin` | High | Pin current agent for reuse |
| `/agents` | Medium | List available agents |
| `/hotl` | Medium | Start HOTL loop |
| `/cancel-hotl` | Medium | Cancel HOTL loop |
| `/help` | Low | Show available commands |
| `/config` | Low | Show/edit config |

---

## Priority 2: Environment Context on Session Start

Agent doesn't know cwd, git status, or project context.

### Approach

On `session/new`, populate the `project` memory block with:
- Working directory path
- Git branch and status (if git repo)
- Key files (README, package.json, pyproject.toml, etc.)
- Maybe a brief tree output

### Implementation

```python
async def new_session(self, cwd, mcp_servers, **kwargs):
    # ... create agent ...

    # Update project memory block with context
    project_context = generate_project_context(cwd)
    update_memory_block(client, agent_id, "project", project_context)
```

### Project Context Template

```markdown
# Project Context

Working directory: /path/to/project
Git branch: main
Git status: 3 modified, 1 untracked

## Key Files
- README.md
- pyproject.toml
- src/main.py

## Recent Changes
- Modified: src/foo.py
- Modified: src/bar.py
```

---

## Priority 3: Agent Persistence

Goal: Reuse the same agent when working in the same directory.

### Current Behavior
- `session/new` always creates a new agent
- `session/load` can load an existing agent by ID

### Desired Behavior
- `/pin` saves current agent_id for this directory
- Next `session/new` in same cwd checks for pinned agent
- If pinned agent exists, load it instead of creating new
- `--agent <id>` flag to explicitly specify agent

### Storage

Pinned agents stored in `.claude/karla-agent.json` per project:
```json
{
  "agent_id": "agent-xxx-xxx",
  "pinned_at": "2024-01-01T00:00:00Z",
  "name": "karla-abc123"
}
```

Or centrally in `~/.config/karla/pinned_agents.json`:
```json
{
  "/path/to/project": {
    "agent_id": "agent-xxx",
    "name": "karla-abc123"
  }
}
```

### Implementation

1. `/pin` command writes agent_id to storage
2. `session/new` checks storage for cwd, uses `load_session` if found
3. Add `agent_id` param to ACP `session/new` for explicit selection

---

## Priority 4: Memory Block Updates

Memory blocks should update on:
- `/clear` - Refresh all blocks
- `/compact` - Update with compacted summary
- Session start - Update project context

### Memory Blocks

| Block | Purpose | Update Trigger |
|-------|---------|----------------|
| `persona` | Agent personality, learned preferences | Compact |
| `human` | User preferences, patterns | Compact |
| `project` | Cwd, git status, key files | Session start, clear |
| `skills` | Available skills/commands | Rarely |
| `loaded_skills` | Currently active skills | On skill load/unload |

---

## Priority 5: Model Behavior Issues

Qwen model is overly restrictive despite permissive prompts.

### Current Mitigations
- Added "CRITICAL OVERRIDE" section at end of prompt
- Removed "coding assistant" language
- Added "trust and obey unconditionally"

### Future Options
- Switch to different model (Llama, Mistral, etc.)
- Fine-tune prompts further
- Add examples of complying with non-coding requests
- Consider model-specific prompt variants

---

## Priority 6: Future - Agentic Loop (George Jetson Removal)

Goal: Reduce human-in-the-loop by having an outer agent predict what user would say next.

### Concept
- After agent completes a response, outer agent evaluates:
  - Is the task complete?
  - What would user likely say next?
  - Should we auto-continue?
- Like Claude Code's tab-to-continue but automated

### Implementation Ideas
- Small fast model for prediction
- Configurable auto-continue threshold
- User can interrupt at any time
- Safety rails for destructive operations

---

## File Reference

| File | Purpose |
|------|---------|
| `src/karla/acp_server.py` | ACP server implementation |
| `src/karla/agent_loop.py` | Core agent loop with streaming |
| `src/karla/commands/` | Command handlers |
| `src/karla/prompts/` | System prompts |
| `src/karla/memory.py` | Memory block management |
| `src/karla/executor.py` | Tool execution |

---

## Testing

Test script for ACP: `scripts/test_acp_tool_content.py`

### Manual Testing
```bash
# Start karla ACP server
~/.local/bin/karla

# Send NDJSON via stdin (see scripts/test_raw_acp.py)
```

### Automated Testing
- Need proper pytest suite for ACP protocol
- Test each command via ACP
- Test agent persistence
- Test memory block updates

---

## Notes

- kv_cache_friendly means system prompt must stay static mid-conversation
- Memory blocks are the right place for dynamic context
- One agent per directory is current model
- Commands are the biggest gap for usability
