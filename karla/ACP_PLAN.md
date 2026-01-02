# Karla ACP Implementation Plan

This document tracks the work needed to make Karla fully functional as an ACP server for IDE integrations.

## Current State

- ✅ Basic ACP server working (`initialize`, `session/new`, `session/prompt`, `session/cancel`)
- ✅ Token streaming working (text streams token-by-token)
- ✅ Tool call delta accumulation (tool args stream correctly)
- ✅ Rich tool content (diffs, commands, locations) streaming to ACP
- ✅ Cancellation working (executor flag checked in agent loop)
- ✅ kv_cache_friendly=True set from config
- ✅ Commands working through ACP (dispatch_command in prompt())
- ✅ `available_commands_update` sent to client on session start (like claude-code-acp)
- ✅ Cwd/environment injected into agent context (update_project_block on session start)
- ✅ Agent persistence (checks pinned agents, then last_agent, saves last_agent)
- ✅ Memory block updates on /clear and /refresh
- ✅ Reasoning/thinking message streaming (agent's internal monologue visible in IDE)
- ✅ Memory tool visibility (archival_memory_*, core_memory_* operations shown as thoughts)

---

## ✅ DONE: Priority 1 - Commands in ACP

Commands now work through ACP:

### Implementation

1. `prompt()` checks if text starts with `/`
2. Routes to `_handle_command()` which uses `dispatch_command()`
3. Returns command output via `session_update` with `agent_message_chunk`
4. Sends `available_commands_update` on session start so IDE knows what commands exist

### Key Changes

- `acp_server.py`: Added `_handle_command()` and `_send_available_commands()`
- Imports `COMMANDS`, `CommandContext`, `dispatch_command` from `karla.commands`
- Uses `update_available_commands()` from `acp.helpers`

---

## ✅ DONE: Priority 2 - Environment Context on Session Start

### Implementation

- `memory.py`: Added `generate_project_context()` and `update_project_block()`
- `acp_server.py`: Calls `update_project_block()` in both `new_session()` and `load_session()`
- Uses `client.agents.blocks.list(agent_id)` to find blocks (not `agent.memory.blocks`)
- Uses `client.blocks.update()` (not `.modify()`)

### Project Context Includes

- Working directory path
- Git branch (if git repo)
- Git status summary (modified/untracked/deleted counts)
- Key project files (README, pyproject.toml, package.json, etc.)

---

## ✅ DONE: Priority 3 - Agent Persistence

### Implementation

On `session/new`:
1. Check for pinned agents via `SettingsManager.get_pinned_agents()`
2. If none, check last agent via `SettingsManager.get_last_agent()`
3. Try to load existing agent with `get_or_create_agent(create_if_missing=False)`
4. Only create new agent if no existing agent found
5. Save agent as last_agent via `settings.save_last_agent()`

### Commands

- `/pin` - Pin current agent (already existed in commands/agents.py)
- `/unpin` - Unpin agent
- `/pinned` - List pinned agents

---

## ✅ DONE: Priority 4 - Memory Block Updates

Memory blocks update on:
- Session start (new or load) - project block refreshed
- `/clear` - clears conversation AND refreshes project block
- `/refresh` - new command, just refreshes project block without clearing

---

## ✅ DONE: Priority 5 - Think Tool & Memory Tool Visibility

### ✅ Reasoning Message Streaming

Added support for streaming the agent's internal thinking to the IDE:

1. **agent_loop.py changes:**
   - Added `ReasoningCallback` type alias
   - Modified `_stream_message` to detect `ReasoningMessage` chunks from Letta
   - Added `on_reasoning` parameter to `run_agent_loop` and `_send_approval`

2. **acp_server.py changes:**
   - Added `on_reasoning_async` callback that calls `update_agent_thought(text_block(reasoning))`
   - Wired up the callback in the `run_agent_loop` call

Now when Letta's agent thinks (sends `ReasoningMessage`), it streams to the IDE as "thinking".

### ✅ Memory Tool Visibility

Added support for displaying internal/server-side tool calls (memory operations):

1. **agent_loop.py changes:**
   - Added `InternalToolCallback` type alias
   - Modified `_stream_message` to detect `ToolCallMessage` chunks (server-side tools)
   - Added `on_internal_tool` parameter throughout the call chain

2. **acp_server.py changes:**
   - Added `on_internal_tool_async` callback that formats memory tools as thoughts:
     - `archival_memory_insert` → "📝 Storing memory: ..."
     - `archival_memory_search` → "🔍 Searching memories: ..."
     - `core_memory_append` → "💭 Updating core memory [field]: ..."
     - `core_memory_replace` → "💭 Replacing core memory [field]"
     - `send_message` → skipped (already visible as text)
     - Other tools → "🔧 tool_name: args"

### Why This Matters
- Transparency: User sees when agent is remembering/recalling things
- Trust: User understands agent's reasoning process
- Debugging: Easier to see why agent behaved a certain way

---

## ✅ DONE: Priority 6 - HOTL (Human-on-the-Loop) Testing

HOTL commands now work through ACP!

### Implementation

1. **acp_server.py changes:**
   - Import `HooksManager` and `create_hotl_hooks`
   - Create hooks manager with HOTL hooks in `new_session()` and `load_session()`
   - Store `hooks_manager` in session state
   - Updated `prompt()` to implement HOTL loop:
     - After `run_agent_loop()` completes, run `on_loop_end` hooks
     - If hook returns `inject_message`, loop again with that message
     - Exit loop when no continuation requested

2. **Test Results:**
   - `/hotl` command starts loop correctly
   - `--max-iterations` cutoff works (tested with 5 iterations)
   - Loop continues via `on_loop_end` hook
   - State persisted in `.karla/hotl-loop.md`

### Key Commands
- `/hotl` - Start HOTL loop ✅
- `/cancel-hotl` - Cancel active loop ✅
- `/hotl-status` - Check loop status ✅
- `/hotl-help` - Show HOTL help ✅

### Known Issue
Minor: Iteration counter increments by 2 instead of 1 per loop (cosmetic, doesn't affect cutoff)

---

## Priority 7: Future - Agentic Loop (George Jetson Removal)

Goal: Reduce human-in-the-loop by having an outer agent predict what user would say next.

### Concept
- After agent completes a response, outer agent evaluates:
  - Is the task complete?
  - What would user likely say next?
  - Should we auto-continue?
- Like Claude Code's tab-to-continue but automated

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
| `src/karla/settings.py` | Settings persistence (pinned agents, last agent) |

---

## Testing

### Test Scripts
- `scripts/test_acp_tool_content.py` - Test tool content streaming
- `scripts/test_raw_acp.py` - Raw NDJSON test
- `scripts/langfuse_traces.py` - View Langfuse telemetry

### Manual Testing
```bash
# Start karla ACP server
~/.local/bin/karla

# Test with Python script
python scripts/test_raw_acp.py
```

---

## API Notes

### Letta Client API
- `client.agents.blocks.list(agent_id)` - Get blocks for agent
- `client.blocks.update(block_id, value=...)` - Update block value
- `client.agents.messages.reset(agent_id, ...)` - Clear conversation

### ACP SDK
- `update_available_commands()` from `acp.helpers` - Send command list to client
- `AvailableCommand` from `acp.schema` - Command definition

---

## Notes

- kv_cache_friendly means system prompt must stay static mid-conversation
- Memory blocks are the right place for dynamic context
- One agent per directory is current model
- Blocks are NOT included in `agent.memory.blocks` from API - use `client.agents.blocks.list()`
