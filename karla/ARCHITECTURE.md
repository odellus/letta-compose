# Karla Architecture

## What is Karla?

Karla is a **Python coding agent** that uses Letta as its backend. It's essentially a Python implementation inspired by Claude Code / Letta Code, providing:

- Client-side tool execution (Read, Write, Edit, Bash, Grep, Glob, etc.)
- Memory blocks for persistent agent state
- ACP (Agent Communication Protocol) server for IDE integration
- HOTL (Human Out of The Loop) mode for autonomous task completion

## Project Structure

```
karla/
├── src/karla/
│   ├── __init__.py
│   ├── agent.py          # Agent creation (create_karla_agent, get_or_create_agent)
│   ├── agent_loop.py     # Core message loop with tool execution
│   ├── acp_server.py     # ACP protocol server for IDE integration
│   ├── cli.py            # Command-line interface
│   ├── config.py         # Configuration loading (karla.yaml)
│   ├── context.py        # AgentContext for shared state across tools
│   ├── executor.py       # ToolExecutor for running tools
│   ├── headless.py       # Non-interactive execution mode
│   ├── hooks.py          # Hook system for events
│   ├── hotl/             # Human Out of The Loop mode
│   ├── letta.py          # Letta integration (register_tools_with_letta)
│   ├── memory.py         # Memory block creation and management
│   ├── prompts/          # System prompts for agents
│   ├── registry.py       # ToolRegistry for managing tools
│   ├── settings.py       # User settings management
│   ├── tool.py           # Base Tool class and ToolDefinition
│   ├── tools/            # All tool implementations
│   │   ├── ask_user.py   # AskUserQuestion
│   │   ├── bash.py       # Bash, BashOutput, KillBash
│   │   ├── edit.py       # Edit (string replacement)
│   │   ├── glob.py       # Glob (file pattern matching)
│   │   ├── grep.py       # Grep (content search)
│   │   ├── plan_mode.py  # EnterPlanMode, ExitPlanMode
│   │   ├── read.py       # Read (file reading)
│   │   ├── skill.py      # Skill (load/unload skills)
│   │   ├── task.py       # Task, TaskOutput (subagents)
│   │   ├── todo.py       # TodoWrite
│   │   ├── web_fetch.py  # WebFetch
│   │   ├── web_search.py # WebSearch
│   │   └── write.py      # Write (file creation)
│   └── commands/         # Slash commands for interactive mode
```

## How It Works

### 1. Agent Creation Flow

```
create_karla_agent()
    │
    ├── Create memory blocks (persona, human, project, skills, loaded_skills)
    │
    ├── client.agents.create(
    │       llm_config=...,
    │       embedding=...,
    │       tools=["memory"],     # Built-in Letta memory tool
    │       block_ids=[...],
    │   )
    │
    └── register_tools_with_letta()
            │
            ├── For each karla tool:
            │   ├── client.tools.upsert(source_code, json_schema)
            │   └── client.agents.tools.attach(agent_id, tool_id)
            │
            └── Returns list of registered tool names
```

### 2. Tool Execution Flow

```
User sends message
    │
    ▼
run_agent_loop()
    │
    ├── Send message to Letta: client.agents.messages.stream()
    │
    ├── Receive response with tool calls (ApprovalRequestMessage)
    │
    ├── For each tool call:
    │   ├── executor.execute(tool_name, args)  # Client-side execution
    │   └── Send result back via approval flow
    │
    └── Repeat until no more tool calls
```

### 3. Tool Registration Details

Each karla tool:
1. Has a `definition()` method returning a `ToolDefinition` (name, description, parameters)
2. Has a `to_letta_source()` method generating a Python stub for Letta
3. Gets registered with `requires_approval=True` so Letta hands control back to client

The Python stub is just:
```python
def ToolName(param1: str, param2: int) -> str:
    """Tool description..."""
    raise Exception("Client-side tool")
```

The actual execution happens in the karla client via `executor.execute()`.

## Key Components

### letta.py - Letta Integration

`register_tools_with_letta(client, agent_id, registry)`:
- Takes a ToolRegistry with all karla tools
- For each tool:
  - Generates Python source stub via `tool.to_letta_source()`
  - Creates JSON schema via `tool.definition().to_openai_schema()`
  - Upserts tool to Letta server
  - Attaches tool to the agent

### agent_loop.py - Message Loop

The core loop that:
- Streams messages from Letta
- Detects tool calls (ApprovalRequestMessage)
- Executes tools client-side
- Sends results back via approval flow
- Handles reasoning/thinking tokens
- Supports hooks for events

### acp_server.py - IDE Integration

Wraps karla as an ACP server that:
- Creates/loads sessions (maps to Letta agents)
- Handles prompts and streams responses
- Converts tool calls to ACP format for rich display
- Supports slash commands

## Configuration (karla.yaml)

```yaml
llm:
  model: "your-model"
  model_endpoint: "http://localhost:1234/v1"
  model_endpoint_type: "openai"
  context_window: 128000

embedding: "ollama/mxbai-embed-large:latest"

server:
  base_url: "http://localhost:8283"  # Letta server
  timeout: null  # No timeout for slow local LLMs

agent_defaults:
  kv_cache_friendly: true
  include_base_tools: true
```

## Running Karla

### Headless Mode
```bash
karla "Create a hello.py file"
karla --continue "Add a function to it"
```

### Interactive Mode
```bash
karla chat
karla chat --continue
```

### ACP Server (for IDE)
```bash
karla-acp
# Or with stdio-to-ws wrapper:
npx stdio-to-ws karla-acp --port 3000
```

## Common Issues

### Tools Not Working
1. Check that `register_tools_with_letta()` is being called after agent creation
2. Verify tools are attached: check Letta server's tool list for the agent
3. Check Langfuse traces to see what tools are in the request

### Agent Not Using Tools
1. The `memory` tool must be included via `tools=["memory"]` in create call
2. Other karla tools must be registered via `register_tools_with_letta()`
3. Check that `requires_approval=True` so tools come back to client

### Method Name Mismatches
After refactoring crow→letta, ensure all method names are aligned:
- `to_letta_source()` in Tool class
- `to_letta_sources()` in ToolRegistry
- `register_tools_with_letta()` in letta.py

## Related Projects

- **crow_ide**: React frontend that connects to karla-acp via WebSocket
- **letta**: The backend server that karla talks to
- **letta-code**: TypeScript version (inspiration for karla)
- **use-acp**: React hooks for ACP clients
