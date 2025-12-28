# Karla Implementation Plan

## Current Status

Karla is a Python-based coding agent using Letta's `kv_cache_friendly=True` for efficient KV cache reuse.

### Completed
- ✅ Core client-side tool execution (Read, Write, Edit, Bash, BashOutput, KillBash, Grep, Glob)
- ✅ Planning tools (EnterPlanMode, ExitPlanMode, TodoWrite)
- ✅ Agent tools (Task, Skill, AskUserQuestion, TaskOutput)
- ✅ Tool registration with Letta via Python stubs + JSON schemas
- ✅ System prompts (`prompts/karla_main.md`, `prompts/persona.md`)
- ✅ CLI headless mode (`karla "prompt"`, `--continue`, `--new`, `--agent`)
- ✅ Settings persistence (`~/.karla/settings.json`, `.karla/settings.local.json`)
- ✅ Memory blocks (persona, human, project, skills, loaded_skills)
- ✅ Memory tool attachment (unified `memory` tool)
- ✅ E2E tests verifying full loop works

### In Progress
- 🔄 Slash commands implementation (see `SLASH_COMMANDS_PLAN.md`)
- 🔄 Interactive CLI mode

## Next Phase: Slash Commands

See `SLASH_COMMANDS_PLAN.md` for detailed implementation plan.

### Priority Commands
| Command | Purpose | Status |
|---------|---------|--------|
| `/clear` | Reset conversation (triggers prompt re-render) | TODO |
| `/compact` | Summarize conversation | TODO |
| `/remember` | Store info to memory blocks | TODO |
| `/init` | Initialize agent memory from project | TODO |
| `/memory` | View current memory blocks | TODO |
| `/help` | List available commands | TODO |

### Interactive Mode
Currently Karla only supports:
- Headless mode: `karla "prompt"`
- Tool testing REPL: `karla repl`

Need to add:
- Interactive chat mode: `karla chat` or `karla -i`
- Slash command support in interactive mode

## Architecture Notes

### kv_cache_friendly
- System prompt stays STATIC during normal conversation
- Memory tool writes go to database, not live prompt
- Prompt updates happen on: `/clear`, `/compact`, new session
- This is intentional - different from letta-code's approach

### Memory Philosophy
- `memory_read`: Agent checks current block state (may differ from snapshot)
- `memory_insert`/`memory_replace`: Writes queue for next session
- `/remember`, `/init`: User-initiated prompt updates

### Tool Execution
- Tools registered as Python stubs on Letta server
- Actual execution happens client-side
- Results sent back via approval flow
- Letta never runs our code

## File Structure

```
src/karla/
├── __init__.py
├── __main__.py           # python -m karla support
├── cli.py                # CLI entry point
├── config.py             # Configuration loading
├── executor.py           # Tool execution
├── registry.py           # Tool registry
├── tool.py               # Tool base class
├── letta.py              # Letta integration
├── memory.py             # Memory block utilities
├── settings.py           # Settings persistence
├── skills.py             # Skill discovery
├── agent_loop.py         # Main agent loop
├── prompts/
│   ├── __init__.py
│   ├── karla_main.md     # System prompt
│   ├── persona.md        # Persona block
│   ├── human.md          # Human block
│   ├── project.md        # Project block
│   └── memory_blocks.py
├── tools/
│   ├── __init__.py
│   ├── read.py, write.py, edit.py
│   ├── bash.py, bash_background.py
│   ├── grep.py, glob.py
│   ├── plan_mode.py, todo.py
│   ├── task.py, skill.py, ask_user.py
│   └── ...
└── commands/             # TODO: Slash commands
    ├── __init__.py
    ├── registry.py
    ├── core.py
    └── prompts.py
```

## Testing

```bash
# Unit tests
uv run pytest tests/ -x -q

# Integration tests (requires Letta server)
uv run pytest tests/test_integration.py -v

# Manual testing
uv run karla "Create hello.py that prints Hello World"
uv run karla --continue "Add a greet function"
uv run karla list
uv run karla repl
```

## Configuration

```yaml
# karla.yaml
server:
  base_url: http://localhost:8283
  timeout: null  # No timeout for local LLMs

llm:
  model: your-model-here
  model_endpoint: http://your-endpoint/v1
  model_endpoint_type: openai
  context_window: 8000

embedding:
  model: ollama/mxbai-embed-large:latest

agent_defaults:
  kv_cache_friendly: true
  include_base_tools: true
```
