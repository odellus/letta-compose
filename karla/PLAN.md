# Karla Implementation Plan

## Goal

Transform Karla into a Python-based coding agent that emulates Letta Code's capabilities while:
1. Using Letta's `kv_cache_friendly=True` configuration for efficiency
2. Running entirely client-side with tools registered via Python stubs
3. Providing a CLI experience similar to Letta Code

## Current State

Based on `LETTACODE_KARLA_COMPARISON.md`, Karla already has:
- ✅ Core client-side tool execution pattern (matches Letta Code)
- ✅ Tool approval flow (matches Letta Code)
- ✅ All core tools: Read, Write, Edit, Bash, BashOutput, KillBash, Grep, Glob
- ✅ Planning tools: EnterPlanMode, ExitPlanMode, TodoWrite
- ✅ Agent tools: Task (stub), Skill (stub), AskUserQuestion
- ✅ Tool registration with Letta via Python stubs + JSON schemas
- ✅ E2E tests that verify the full loop works

## Implementation Phases

### Phase 1: System Prompts (Priority: HIGH)

**Goal:** Create rich system prompts that match Letta Code's structure.

**Files to create:**
```
src/karla/prompts/
├── __init__.py
├── karla_main.md        # Main system prompt (based on letta_claude.md)
├── persona.md           # Default persona block
└── memory_blocks.py     # Memory block loading utilities
```

**System prompt sections (from letta_claude.md):**
1. Identity and purpose
2. Tone and style
3. Professional objectivity
4. Planning without timelines
5. Task Management (TodoWrite usage)
6. Asking questions (AskUserQuestion usage)
7. Doing tasks (read before modify, security, avoid over-engineering)
8. Tool usage policy (prefer specialized tools, parallel calls)
9. Code references (file_path:line_number format)

**Key adaptations for Karla:**
- Replace "Letta Code" with "Karla"
- Remove Memory and Skills sections (Phase 2 & 3)
- Focus on Python-centric development

**Implementation:**
```python
# src/karla/prompts/__init__.py
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_system_prompt(name: str = "karla_main") -> str:
    """Load a system prompt by name."""
    prompt_file = PROMPTS_DIR / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"System prompt not found: {name}")
    return prompt_file.read_text()

def get_default_system_prompt() -> str:
    """Get the default Karla system prompt."""
    return load_system_prompt("karla_main")
```

---

### Phase 2: CLI Enhancements (Priority: HIGH)

**Goal:** Create a CLI that matches Letta Code's headless and interactive modes.

**Current CLI:** Basic REPL for testing tools
**Target CLI:** Full agent interaction with:
- Headless mode (pipe input, get output)
- Interactive TUI mode
- Agent persistence (continue sessions)
- Output formats (text, json, stream-json)

**New CLI structure:**
```
karla [OPTIONS] [PROMPT]       # Headless mode with prompt
karla repl                     # Interactive REPL (current)
karla --new                    # Force new agent
karla --continue              # Continue last agent
karla --agent <id>            # Use specific agent
karla --model <handle>        # Override model
karla --output-format <fmt>   # text|json|stream-json
```

**Files to modify/create:**
```
src/karla/
├── cli.py                    # Extend with full CLI
├── headless.py              # New: headless execution mode
├── agent_loop.py            # New: main agent message loop
└── settings.py              # New: settings persistence
```

**Key functions from Letta Code headless.ts:**
1. `resolveAllPendingApprovals()` - Clear pending approvals before new input
2. Main loop: send message → receive response → handle tool calls → repeat
3. Output formatting (text/json/stream-json)
4. Error handling with retries

**Implementation:**
```python
# src/karla/agent_loop.py
async def run_agent_loop(
    client: Letta,
    agent_id: str,
    executor: ToolExecutor,
    initial_message: str,
    output_format: str = "text",
) -> str:
    """Run the main agent loop with tool execution."""

    pending_messages = [{"role": "user", "content": initial_message}]

    while True:
        response = client.agents.messages.create(
            agent_id=agent_id,
            messages=pending_messages,
        )

        pending_messages = []
        tool_calls = []

        for msg in response.messages:
            msg_type = type(msg).__name__

            if msg_type == "ApprovalRequestMessage":
                # Execute tool and queue approval
                tool_call = msg.tool_call
                result = await executor.execute(
                    tool_call.name,
                    json.loads(tool_call.arguments)
                )

                tool_calls.append({
                    "type": "tool",
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_return": result.output,
                    "status": "error" if result.is_error else "success",
                })

        if tool_calls:
            pending_messages = [{
                "type": "approval",
                "approvals": tool_calls,
            }]
            continue

        # No more tool calls - extract final response
        return extract_final_response(response)
```

---

### Phase 3: Memory Blocks Integration (Priority: MEDIUM)

**Goal:** Integrate with Letta's memory system for persistent agent state.

**Memory blocks to implement:**
1. `persona` - Agent identity and learned preferences
2. `skills` - Available skills directory
3. `loaded_skills` - Currently loaded skills

**Implementation approach:**
1. Create memory blocks on agent creation
2. Use Letta's built-in `memory` tool for updates
3. Load persona from `prompts/persona.md`

**Files to create:**
```
src/karla/
├── memory.py                 # Memory block utilities
└── prompts/persona.md        # Default persona content
```

**Agent creation with memory:**
```python
# src/karla/agent.py
async def create_agent(
    client: Letta,
    name: str,
    config: KarlaConfig,
    working_dir: str,
) -> AgentState:
    """Create a new Karla agent with memory blocks."""

    # Load default memory blocks
    persona_content = load_prompt("persona")

    # Create memory blocks
    persona_block = client.blocks.create({
        "label": "persona",
        "description": "Agent identity and learned preferences",
        "value": persona_content,
    })

    # Create agent with memory
    agent = client.agents.create(
        name=name,
        system=get_default_system_prompt(),
        llm_config=config.llm.to_dict(),
        embedding="letta/letta-free",
        tools=get_tool_names(),
        block_ids=[persona_block.id],
        include_base_tools=True,  # Include memory tool
        kv_cache_friendly=True,
    )

    return agent
```

---

### Phase 4: Settings Persistence (Priority: MEDIUM)

**Goal:** Persist agent IDs and settings across sessions.

**Settings files:**
```
~/.karla/settings.json        # Global settings
.karla/settings.local.json    # Project settings
```

**Settings structure:**
```python
@dataclass
class KarlaSettings:
    last_agent: str | None = None
    default_model: str | None = None

@dataclass
class ProjectSettings:
    last_agent: str | None = None
```

**Implementation:**
```python
# src/karla/settings.py
class SettingsManager:
    def __init__(self):
        self.global_path = Path.home() / ".karla" / "settings.json"
        self.local_path = Path.cwd() / ".karla" / "settings.local.json"

    def get_last_agent(self) -> str | None:
        """Get last agent ID (project first, then global)."""
        local = self.load_local()
        if local and local.last_agent:
            return local.last_agent

        global_ = self.load_global()
        if global_ and global_.last_agent:
            return global_.last_agent

        return None

    def save_last_agent(self, agent_id: str):
        """Save agent ID to both project and global settings."""
        self.update_local({"last_agent": agent_id})
        self.update_global({"last_agent": agent_id})
```

---

### Phase 5: Skills System (Priority: LOW)

**Goal:** Full skill loading/unloading with memory blocks.

**Skill directory structure:**
```
.skills/
├── commit/
│   └── SKILL.md
├── review-pr/
│   └── SKILL.md
└── ...
```

**Skill discovery:**
```python
# src/karla/skills.py
@dataclass
class Skill:
    id: str
    name: str
    description: str
    path: Path
    content: str

async def discover_skills(skills_dir: Path) -> list[Skill]:
    """Discover skills from .skills directory."""
    skills = []

    for skill_path in skills_dir.glob("*/SKILL.md"):
        content = skill_path.read_text()
        metadata = parse_yaml_frontmatter(content)

        skills.append(Skill(
            id=skill_path.parent.name,
            name=metadata.get("name", skill_path.parent.name),
            description=metadata.get("description", ""),
            path=skill_path.parent,
            content=content,
        ))

    return skills

def format_skills_for_memory(skills: list[Skill]) -> str:
    """Format skills list for the skills memory block."""
    lines = ["# Available Skills", ""]
    for skill in skills:
        lines.append(f"- **{skill.id}**: {skill.description}")
    return "\n".join(lines)
```

---

### Phase 6: Tool Descriptions Enhancement (Priority: LOW)

**Goal:** Match Letta Code's rich tool descriptions.

**Key additions to Bash tool:**
- Git commit instructions with proper format
- PR creation instructions
- Security warnings

**Implementation:** Update `src/karla/tools/bash.py` with full description from letta-code's `Bash.md`.

---

## Implementation Order

1. **Phase 1: System Prompts** - Foundation for agent behavior
2. **Phase 2: CLI Enhancements** - Core user experience
3. **Phase 4: Settings Persistence** - Session continuity (needed for Phase 2)
4. **Phase 3: Memory Blocks** - Enhanced agent capabilities
5. **Phase 6: Tool Descriptions** - Polish
6. **Phase 5: Skills System** - Advanced feature

---

## Testing Plan

### Unit Tests
- Prompt loading
- Settings persistence
- Skill discovery

### Integration Tests
- Agent creation with memory blocks
- CLI headless mode
- Agent session continuity

### E2E Tests (Agent using Karla)
1. Create a Python file, run it, verify output
2. Read a file, modify it, verify changes
3. Multi-step workflow (read → edit → test → commit)
4. Session continuity (start task → exit → resume)

---

## Success Criteria

Karla is complete when:

1. ✅ `karla "Create hello.py that prints 'Hello World'"` works end-to-end
2. ✅ `karla --continue "Now add a function"` resumes the previous session
3. ✅ Agent uses TodoWrite for planning
4. ✅ Agent follows system prompt guidelines (no over-engineering, etc.)
5. ✅ Tool descriptions include git commit format
6. ✅ E2E test passes: agent solves a real coding task

---

## Configuration Notes

### kv_cache_friendly

Letta's `kv_cache_friendly=True` configuration enables:
- Efficient KV cache reuse across turns
- Reduced latency for multi-turn conversations
- Better performance for agentic workflows

This should be set on agent creation:
```python
agent = client.agents.create(
    ...,
    kv_cache_friendly=True,
)
```

### Model Selection

For local development with lm-studio:
- Model: whatever is loaded in lm-studio
- Endpoint: `http://coast-after-3:1234/v1`
- Timeout: 600s (local models are slow)

For production:
- Use provider's optimal model (Claude, GPT-4, etc.)
- Standard timeouts

---

## Dependencies

### Python packages needed:
- `letta-client` - Letta API client (already have)
- `rich` - TUI rendering (for interactive mode)
- `pyyaml` - YAML frontmatter parsing

### No new dependencies for Phase 1-2:
- Can start immediately with existing dependencies
