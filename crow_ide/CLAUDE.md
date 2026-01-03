# Claude Code Guide for Crow IDE

## Project Overview

Crow IDE is a web-based IDE with an integrated AI coding agent. It consists of:

- **Frontend** (`frontend/`): React + TypeScript + Vite app with file tree, agent chat panel, and terminal
- **Backend** (`server.py`): Starlette server that serves the frontend and proxies to the agent
- **ACP Bridge** (`acp_bridge.py`): WebSocket proxy between frontend and karla-acp agent
- **Karla** (`../karla/`): The Python coding agent that powers the IDE

## Architecture

```
Browser <-> Crow IDE Server (:8000) <-> ACP Bridge <-> karla-acp (:3000) <-> Letta Server (:8283) <-> Local LLM
```

## Working with the Local LLM

**CRITICAL**: The local LLM (Qwen3-80B via LM Studio) is SLOW. Expect:

- **~50 seconds** for the initial LLM call to complete
- **1-5 minutes** for streaming response depending on complexity
- **Longer for complex queries** that require tool usage or long context

### Timeout Guidelines

When testing the agent via Playwright:

| Query Type | Expected Wait Time |
|------------|-------------------|
| Simple greeting ("hi") | 2-4 minutes |
| Math questions | 2-4 minutes |
| File operations (Glob, Read) | 3-5 minutes |
| Code analysis | 5-10 minutes |
| Complex multi-tool tasks | 10+ minutes |

**DO NOT** give up after 2 minutes. The LLM is working, just slowly.

### Context Management

The local LLM slows down significantly with large context. **Always**:

1. Use `/clear` at the start of a new testing session
2. Use `/compact` periodically during extended conversations
3. Keep test prompts concise

If responses start timing out after working earlier, the context has grown too large. Clear and restart.

## Running the System

### Prerequisites

Ensure these are running:
1. **Letta Server**: `docker` container on port 8283
2. **LM Studio**: Local LLM server

### Start Commands

```bash
# Terminal 1: Start the Crow IDE server
cd /home/thomas/src/projects/letta-proj
uvicorn crow_ide.server:app --port 8000

# Terminal 2: Start the ACP agent bridge
cd /home/thomas/src/projects/letta-proj/karla
npx stdio-to-ws karla-acp --port 3000
```

### Verify Health

```bash
curl http://localhost:8000/api/health
# Should return: {"status":"ok"}
```

## Testing

### Backend Tests

```bash
cd /home/thomas/src/projects/letta-proj
pytest crow_ide/tests/
```

### Frontend Build

```bash
cd /home/thomas/src/projects/letta-proj/crow_ide/frontend
pnpm build
```

### E2E Testing with Playwright

When using Playwright to test the agent:

1. Navigate to `http://localhost:8000`
2. Wait for "Ready" status
3. Send `/clear` first to reset context
4. Wait for response before sending next message
5. **Be patient** - local LLM is slow

## Ralph Loop (Iterative Development)

The Ralph Loop is a 6-phase development/verification cycle:

### Phase 1: Backend Tests Pass
```bash
pytest crow_ide/tests/
```

### Phase 2: Frontend Builds
```bash
cd crow_ide/frontend && pnpm build
```

### Phase 3: Server Runs
Start uvicorn on :8000, verify health check passes.

### Phase 4: E2E Playwright Verification
Navigate to localhost:8000, verify:
- File tree visible
- Agent panel visible
- Terminal visible

### Phase 5: Agent Works
Send a message, verify response received.

### Phase 6: Prompt Tuning
Continuous testing loop. Track success rate. Need 10 consecutive checks at >= 95% success.

**Important for Phase 6:**
- Checks should test ACTUAL coding capabilities, not just math
- Good checks: file listing, code reading, code explanation, tool usage
- Bad checks: "2+2", "hi", simple arithmetic
- Track results in `RALPH_STATE.md`

### Meaningful Phase 6 Checks

Examples of substantive checks:
1. "List the Python files in this project" (tests Glob tool)
2. "Read server.py and explain the main endpoints" (tests Read + comprehension)
3. "Find all functions that handle WebSocket connections" (tests Grep)
4. "What dependencies does this project have?" (tests file reading)
5. "Explain how the ACP bridge works" (tests multi-file understanding)
6. "Create a simple test for the health endpoint" (tests code generation)

## Common Issues

### Session Not Found

If you see "Session not found" errors, the karla-acp process was restarted but the browser has an old session ID.

**Fix**: Clear localStorage and refresh:
```javascript
localStorage.clear(); location.reload();
```

### Agent Stuck on "Processing..."

The agent is not stuck - the local LLM is just slow. Wait longer (5-10 minutes for complex queries).

If still stuck after 10+ minutes:
1. Check `/tmp/karla-acp.log` for errors
2. Verify Letta server is running
3. Verify LM Studio is running
4. Clear context and retry

### Response Timeouts After POST Completes

The HTTP POST to Letta completes but no text streams back. This usually means:
- LLM is generating a very long response
- Context is too large, slowing generation
- Wait longer, or `/clear` and retry with shorter context

## File Locations

| File | Purpose |
|------|---------|
| `server.py` | Main Starlette server |
| `acp_bridge.py` | WebSocket proxy to karla-acp |
| `frontend/src/` | React frontend source |
| `tests/` | Backend and E2E tests |
| `RALPH_STATE.md` | Ralph Loop progress tracking |
| `PROGRESS.md` | General development progress |
| `/tmp/karla-acp.log` | ACP server logs |

## Karla Agent

The agent is in `../karla/src/karla/`:

| File | Purpose |
|------|---------|
| `acp_server.py` | ACP protocol implementation |
| `agent.py` | Agent creation and management |
| `agent_loop.py` | Main agent conversation loop |
| `tools/` | Tool implementations (Read, Write, Bash, etc.) |
| `letta.py` | Letta backend integration |

## ACP Protocol (Agent Client Protocol)

ACP is a JSON-RPC 2.0 based protocol for communication between AI agents and clients (editors, IDEs).

### Protocol Resources

| Resource | Location |
|----------|----------|
| Python SDK | `../python-sdk/` - Install: `pip install agent-client-protocol` |
| Claude Code ACP | `../claude-code-acp/` - Reference implementation |
| crow_agent docs | `../crow_agent/docs/src/acp/` - Protocol deep-dives |
| use-acp (React) | Frontend uses `use-acp` npm package for ACP client |
| Official site | https://agentclientprotocol.com/ |
| Zulip community | https://agentclientprotocol.zulipchat.com/ |

### Key ACP Methods

| Method | Direction | Description |
|--------|-----------|-------------|
| `initialize` | Client → Agent | Initialize the connection |
| `session/new` | Client → Agent | Create a new session |
| `session/prompt` | Client → Agent | Send a prompt to the agent |
| `session/cancel` | Client → Agent | Cancel an ongoing operation |

### Session Update Notifications (Agent → Client)

| Update Type | Description |
|-------------|-------------|
| `agent_message_chunk` | Text content streaming |
| `agent_thought_chunk` | Reasoning/thinking content |
| `tool_call` | Tool execution started |
| `tool_call_update` | Tool execution completed/status |
| `plan` | Todo list updates |

### Tool Call Status Values

Tool calls have a `status` field that should be reflected in the UI:
- `pending` - Tool call queued
- `in_progress` - Tool is executing (show spinner)
- `completed` - Tool finished successfully (show checkmark)
- `failed` - Tool execution failed (show error icon)

## Playwright Testing Methodology

Claude Code uses Playwright to visually test and compare agent implementations.

### Side-by-Side Testing

When developing Crow IDE, test the same prompts against **both** Crow IDE and Claude Code to:
1. Compare model performance and response quality
2. Learn from Claude Code's UI/UX patterns
3. Identify features to port to Crow IDE
4. Verify ACP protocol compliance

### Running Side-by-Side Tests

```bash
# Terminal 1: Crow IDE
uvicorn crow_ide.server:app --port 8000
# Test at http://localhost:8000

# Terminal 2: Claude Code (via claude-code-acp)
npx @zed-industries/claude-code-acp
# Or use Zed editor's agent panel
```

### What to Compare

| Aspect | What to Look For |
|--------|------------------|
| Tool call display | Spinners, status icons, collapsible details |
| Streaming | Real-time text appearance, chunking |
| Error handling | How errors are shown, retry options |
| Markdown rendering | Code blocks, mermaid, latex |
| Session management | Tab switching, history, context clearing |

### Testing Methodology Loop

1. **Identify feature** - Pick a UI/UX feature to test
2. **Test in Claude Code** - Take screenshots, note behavior
3. **Test in Crow IDE** - Compare against Claude Code
4. **Document differences** - Note what Claude Code does better
5. **Implement improvements** - Port good patterns to Crow IDE
6. **Re-test** - Verify the improvement works

This approach leverages Claude's intimate knowledge of its own tooling (tool descriptions are in context) to improve Crow IDE.

## Patience Reminders

1. Local LLM is slow - that's okay
2. 5-minute waits are normal
3. Don't shortcut with trivial tests
4. Quality checks > fast completion
5. Clear context when things slow down
6. The infrastructure works - trust it
