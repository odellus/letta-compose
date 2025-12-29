# Karla

Python coding agent with Letta backend and client-side tool execution.

## Setup

```bash
# Create standalone venv and install
uv venv
uv pip install -e .

# Or with dev dependencies
uv pip install -e ".[dev]"
```

Requires a running Letta server (default: `http://localhost:8283`).

## Configuration

Create `karla.yaml` in your project root:

```yaml
providers:
  moonshot:
    type: api
    api_key: ${MOONSHOT_API_KEY}
    base_url: http://your-llm-server:1234/v1

llm:
  provider: moonshot
  model: your-model-name
  model_endpoint_type: openai
  context_window: 120000

embedding:
  model: ollama/mxbai-embed-large:latest

server:
  base_url: http://localhost:8283
  timeout: null  # no timeout for slow local LLMs
```

Create `.env` for secrets:

```bash
MOONSHOT_API_KEY=your-key-here
```

## CLI Usage

```bash
# Single prompt (headless mode)
karla "Create a hello.py file"

# Interactive mode
karla chat

# Continue last agent session
karla chat --continue

# Force new agent
karla chat --new

# List available tools
karla list
```

## Tools

Karla has client-side tool execution - tools run on your machine, not the server:

- **Read/Write/Edit** - File operations
- **Bash** - Shell commands with background process support
- **Glob/Grep** - File search
- **WebSearch/WebFetch** - Web access
- **Task** - Spawn subagents (HOTL mode)
- **TodoWrite** - Task tracking
- **Skill** - Load/unload skills

## Debug/Telemetry

View Langfuse traces (requires Langfuse running):

```bash
# List recent traces
python scripts/langfuse_traces.py

# Get LLM calls as JSON (pipe to jq)
python scripts/langfuse_traces.py <trace_id> --llm | jq '.[0].response_data'
```

## Streaming (Letta)

Letta supports SSE streaming via:
- `client.agents.messages.stream()` - step streaming (default)
- `stream_tokens=True` - token streaming

Endpoints:
- `/v1/agents/{agent_id}/messages/stream`
- `/v1/runs/{run_id}/stream`

## ACP Server

Karla can run as an ACP (Agent Communication Protocol) server:

```bash
karla-acp
```

This starts an ACP server that streams:
- `AgentMessageChunk` - agent text responses
- `ToolCallStart` - tool call begins (with kind, locations, raw_input)
- `ToolCallProgress` - tool call completion (with raw_output)

ACP clients can connect and send prompts. Each session creates a new Letta agent
or continues an existing one.

## License

MIT
