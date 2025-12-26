# Karla - Python Coding Agent on Letta

## Overview

Karla is a Python coding agent built on the Letta framework. It provides Claude Code-like functionality (file operations, shell execution, code search) with Letta's stateful agent capabilities (persistent memory, conversation history, tool management).

The key architectural decision: **tools execute client-side**. Letta manages the agent's state and LLM interactions, but when the agent calls a tool like `Read` or `Bash`, the actual execution happens on the client machine. This is the HOTL (Humans Out of The Loop) pattern - tools auto-execute without approval prompts.

## Project Status

**Current State**: Foundation complete, evals passing

- Tool registration with Letta working (strict mode schemas for llama.cpp)
- Client-side tool execution working
- Eval framework extended to support client-side tools
- 5/5 basic eval cases passing (0.95 avg score)

**What Works**:
- File tools: Read, Write, Edit
- Shell tools: Bash, BashOutput, KillBash
- Search tools: Grep, Glob
- Planning tools: TodoWrite, EnterPlanMode, ExitPlanMode
- Agent tools: Task, TaskOutput, Skill, AskUserQuestion

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Karla Client                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Tool        │  │ Tool        │  │ Agent Loop          │  │
│  │ Registry    │──│ Executor    │──│ (send msg, execute  │  │
│  │             │  │             │  │  tools, send result)│  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Letta Server                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Agent State │  │ Memory      │  │ LLM Provider        │  │
│  │ & History   │  │ Blocks      │  │ (llama.cpp/OpenAI)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Tool Execution Flow

1. Client sends user message to Letta agent
2. Agent decides to call a tool (e.g., `Read`)
3. Letta returns `stop_reason: requires_approval` with tool call details
4. Client executes tool locally using `ToolExecutor`
5. Client sends `ToolReturnParam` with result back to agent
6. Agent processes result, may call more tools or respond
7. Loop continues until `stop_reason: end_turn`

## Key Files

### Core Module (`src/karla/`)

| File | Purpose |
|------|---------|
| `tool.py` | Base `Tool` class, `ToolDefinition` with strict mode schemas |
| `letta.py` | `register_tools_with_letta()`, `LettaAgent` wrapper |
| `executor.py` | `ToolExecutor` - runs tools by name |
| `registry.py` | `ToolRegistry` - collection of tools |
| `tools/` | Individual tool implementations |

### Tool Implementation Pattern

```python
class ReadTool(Tool):
    @property
    def name(self) -> str:
        return "Read"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="Read",
            description="Reads a file from the filesystem...",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "..."},
                    # ... more params
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, args: dict, ctx: ToolContext) -> ToolResult:
        # Actual implementation
        content = Path(args["file_path"]).read_text()
        return ToolResult.success(content)
```

### Strict Mode (Critical for llama.cpp)

Tool schemas must be in strict mode for llama.cpp grammar parsing:

```python
def to_openai_schema(self, strict: bool = True) -> dict:
    params = dict(self.parameters)
    if strict:
        # ALL params in required array (even optional ones)
        params["required"] = list(params.get("properties", {}).keys())
        params["additionalProperties"] = False
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": params,
            "strict": strict,
        },
    }
```

## Development

### Prerequisites

- Letta server running on `localhost:8283`
- LLM server (llama.cpp) on `coast-after-3:1234` or configure your own
- Python 3.11+, uv package manager

### Running Evals

```bash
cd karla

# Set LLM endpoint (uses OpenAI-compatible API)
export OPENAI_BASE_URL=http://coast-after-3:1234/v1
export OPENAI_API_KEY=dummy

# Run eval suite
uv run letta-evals run evals/suite.yaml --max-concurrent 1

# With output directory
uv run letta-evals run evals/suite.yaml -o /tmp/eval-output
```

### Eval Suite Structure

```yaml
# evals/suite.yaml
name: karla-tools-basic
dataset: dataset.jsonl
setup_script: setup.py:prepare_eval_environment

target:
  kind: letta_agent
  agent_script: create_agent.py:create_karla_agent
  tool_executor_script: tool_executor.py:execute_tool  # Client-side execution
  base_url: http://localhost:8283
  max_tool_iterations: 20

graders:
  correctness:
    kind: model_judge
    model: Qwen3-Coder-30B-A3B-UD-Q4_K_XL
    provider: openai  # Uses OPENAI_BASE_URL
    prompt: |
      Evaluate whether the coding agent correctly completed the task...

gate:
  kind: simple
  metric_key: correctness
  aggregation: avg_score
  op: gte
  value: 0.7
```

### Adding New Tools

1. Create tool file in `src/karla/tools/`
2. Implement `Tool` interface with `name`, `definition()`, `execute()`
3. Register in `src/karla/tools/__init__.py`
4. Add to `create_default_registry()`

### Testing a Single Tool

```python
import asyncio
from karla.tools import create_default_registry
from karla.executor import ToolExecutor

async def test():
    registry = create_default_registry("/tmp/test")
    executor = ToolExecutor(registry, "/tmp/test")
    
    result = await executor.execute("Read", {"file_path": "/tmp/test/foo.txt"})
    print(result.output, result.is_error)

asyncio.run(test())
```

## Roadmap

### Phase 1: Foundation (Complete)
- [x] Tool base classes and registry
- [x] Letta integration with strict mode schemas
- [x] Client-side tool execution
- [x] Basic eval framework with tool executor support
- [x] Core tools (Read, Write, Edit, Bash, Grep, Glob)

### Phase 2: Agent Client
- [ ] CLI interface for interactive use
- [ ] Streaming response display
- [ ] Tool execution progress/output display
- [ ] Conversation history management
- [ ] Agent persistence (save/load agents)

### Phase 3: Enhanced Capabilities
- [ ] Web search tool
- [ ] Multi-file refactoring
- [ ] Git operations
- [ ] Project context awareness
- [ ] Skills system (loadable tool sets)

### Phase 4: Multi-Agent
- [ ] ACP (Agent Communication Protocol) integration
- [ ] Sub-agent spawning for complex tasks
- [ ] Agent coordination patterns

## Technical Notes

### Why Client-Side Tools?

1. **Security**: File/shell operations run with user's permissions, not server's
2. **Flexibility**: Tools can access local resources, networks, hardware
3. **Simplicity**: No need to sandbox or containerize on server

### letta-evals Fork

We maintain a fork of `letta-evals` that adds client-side tool execution support. Key changes:

- `LettaAgentTarget` accepts `tool_executor` callback
- Stream processing detects `requires_approval` and collects tool calls
- Tool results sent back via `ToolReturnParam`
- Trajectory includes messages from all runs (not just final)

### LLM Compatibility

Tested with:
- Qwen3-Coder-30B-A3B via llama.cpp (requires strict mode)
- Should work with any OpenAI-compatible endpoint

The strict mode schema format is critical for llama.cpp - without it, grammar parsing fails with cryptic errors about empty stacks.

## Related Projects

- [letta](https://github.com/letta-ai/letta) - The agent framework
- [letta-python](https://github.com/letta-ai/letta-python) - Python SDK
- [letta-code](https://github.com/letta-ai/letta-code) - Reference coding agent (TypeScript)
- [letta-evals](https://github.com/letta-ai/letta-evals) - Evaluation framework (our fork)
