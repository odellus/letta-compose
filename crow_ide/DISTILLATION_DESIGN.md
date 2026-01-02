# Karla Distillation System Design

## Vision

Train Karla by distilling Claude Code's capabilities. Capture Claude Code solving problems, then use those demonstrations as training data for Karla.

---

# Crow IDE Roadmap

## Existing Infrastructure

**Langfuse Tracing** - Already working!
- `karla/scripts/langfuse_traces.py` captures Letta/Karla traces
- Can retrieve full LLM request/response with `--llm` flag
- This is foundational - we have observability

## IDE Features Needed

### Multiple Terminals (Priority)
- Current: Single terminal panel at bottom
- Needed:
  - **Plus button** to create new terminals
  - **Draggable/floating** terminal windows
  - Tab system or window management for multiple terminals
  - Each terminal is independent PTY session

### UI Inspiration: Marimo
- Marimo has sophisticated cell/panel management
- Need to spelunk marimo codebase for:
  - Draggable panel implementation
  - Window/tab management patterns
  - Resizable split views
  - Floating windows

### Other IDE Features to Explore
- [ ] Split views (horizontal/vertical)
- [ ] Floating/dockable panels
- [ ] File tabs (open multiple files)
- [ ] Minimap
- [ ] Search across files
- [ ] Git integration panel
- [ ] Output/logs panel separate from terminal

## Marimo Code Exploration TODO

Look at marimo's frontend for:
1. Panel/window management system
2. Drag and drop implementation
3. State management for multiple panels
4. Terminal implementation (if they have one)
5. Layout persistence

Key directories to explore:
- `marimo/frontend/src/components/`
- `marimo/frontend/src/core/`
- Look for: drag, panel, window, layout, split, dock

---

## Session Persistence (Priority 1)

### Goals
- Persist all agent sessions to a database
- Enable replaying/reviewing sessions
- Capture full conversation context including system prompts
- Support both Karla and Claude Code sessions

### Data to Capture

**For Karla (via Letta):**
- Session ID
- System prompt (Letta mutates this rather than destroying context on "new session")
- All messages (user, assistant, tool calls, tool results)
- Timestamps
- Model used
- Token counts if available

**For Claude Code (via ACP):**
- Session ID
- All ACP notifications (the full stream we already receive)
- Tool calls and results
- System prompt/rules files attached
- Possibly OTEL traces (Claude Code may support this)

### Implementation Ideas

1. **Database Schema**
```sql
-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    agent_type TEXT NOT NULL,  -- 'karla', 'claude', etc.
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    system_prompt TEXT,
    metadata JSONB
);

-- Messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    role TEXT,  -- 'user', 'assistant', 'tool_call', 'tool_result'
    content JSONB,
    timestamp TIMESTAMP,
    sequence_number INTEGER
);

-- Tool calls table (normalized)
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY,
    message_id UUID REFERENCES messages(id),
    tool_name TEXT,
    arguments JSONB,
    result JSONB,
    duration_ms INTEGER
);
```

2. **ACP Bridge Modifications**
   - Intercept all WebSocket messages in `acp_bridge.py`
   - Write to database before forwarding
   - Could use SQLite for simplicity or PostgreSQL for production

3. **Letta Integration**
   - Letta stores conversations internally
   - May need to query Letta's API or database directly
   - Or intercept at the karla-acp layer

### OTEL for Claude Code
- Read that Claude Code supports OpenTelemetry
- Could export traces to Langfuse or similar
- Would give us full visibility into Claude Code's reasoning

## Curriculum Design (Priority 2)

### Philosophy
- Start simple, progress to complex
- Cover each tool individually first
- Then combinations of tools
- Then multi-step reasoning tasks
- Most problems should be trivially solvable by Claude Code

### Tool Coverage Matrix

| Tool | Simple | Medium | Hard |
|------|--------|--------|------|
| Glob | Find `*.py` files | Find files matching multiple patterns | Complex exclusions |
| Read | Read single file | Read specific lines | Parse and extract |
| Write | Create new file | Modify existing | Multi-file changes |
| Edit | Single line change | Multi-line edit | Refactoring |
| Bash | Simple command | Piped commands | Complex scripts |
| Grep | Simple pattern | Regex patterns | Multi-file search |
| Task | Single subtask | Parallel tasks | Dependent tasks |

### Curriculum Levels

**Level 1: Single Tool, Explicit Instructions**
- "List all Python files in this directory" (Glob)
- "Read the contents of server.py" (Read)
- "Create a file called hello.py with print('hello')" (Write)
- "Run `ls -la`" (Bash)

**Level 2: Single Tool, Implicit Instructions**
- "What Python files exist here?" (Glob - must infer pattern)
- "What does the server do?" (Read - must find and read server.py)
- "Add a hello world script" (Write - must decide filename/content)

**Level 3: Multi-Tool, Explicit**
- "Find all test files and count the lines in each" (Glob + Read/Bash)
- "Read server.py and add a comment at the top" (Read + Edit)
- "Find functions that use 'async' and list them" (Grep + Read)

**Level 4: Multi-Tool, Implicit**
- "How many lines of Python code are in this project?" (Glob + Read + count)
- "What's the test coverage structure?" (Glob + Read + analyze)
- "Add logging to the main endpoint" (Read + understand + Edit)

**Level 5: Complex Reasoning**
- "Fix the bug in the authentication flow" (multi-file understanding)
- "Refactor the database layer to use async" (architectural changes)
- "Add a new API endpoint with tests" (multiple file creation)

### Dataset Generation Process

1. **Define Problem**
   - Write clear problem statement
   - Specify expected outcome
   - Tag with tools needed, difficulty level

2. **Claude Code Solves**
   - Feed problem to Claude Code
   - Capture full session (all tool calls, reasoning)
   - Verify solution works

3. **Extract Training Data**
   - Input: Problem + context (files, system state)
   - Output: Sequence of (thought, action, observation)
   - Could be used for:
     - Supervised fine-tuning
     - RLHF reward modeling
     - Distillation into smaller model

4. **Quality Filtering**
   - Remove failed attempts
   - Filter out unnecessarily complex solutions
   - Prefer minimal tool usage for simple problems

## System Prompts & Tool Descriptions

### Karla's Current Tools
Need to document:
- Each tool's name and description
- Parameter schemas
- Example usage
- Common patterns

### System Prompt Evolution
- Track how system prompts change over time
- A/B test different prompt versions
- Correlate prompt changes with success rates

## Technical Notes

### Letta Quirks
- "New session" doesn't destroy context, mutates system prompt
- Need to understand exactly what state persists
- May need to query Letta's internal storage

### ACP Protocol
- Already receiving full notification stream
- Tool calls come through as structured data
- Could log everything with minimal changes

## Next Steps

1. [ ] Add session persistence to acp_bridge.py (SQLite first)
2. [ ] Create simple UI to browse past sessions
3. [ ] Document all Karla tools with examples
4. [ ] Write first 10 Level 1 curriculum problems
5. [ ] Set up Claude Code with OTEL if possible
6. [ ] Create problem-solution pair extraction script

## Files to Modify

| File | Change |
|------|--------|
| `crow_ide/acp_bridge.py` | Add database logging |
| `crow_ide/server.py` | Add session history API endpoints |
| `crow_ide/frontend/src/components/acp/` | Add session browser UI |
| `karla/src/karla/acp_server.py` | Ensure all data is exposed |

## Questions to Answer

1. Can we get Claude Code's system prompt from the ACP stream?
2. Does Letta expose conversation history via API?
3. What OTEL exporters does Claude Code support?
4. Should we use the same DB schema for both agents or separate?
