# Letta Code vs Karla Comparison

This document analyzes the differences between Letta Code and Karla for reproducing basic Letta Code functionality.

## Executive Summary

Karla has implemented the core client-side tool execution pattern from Letta Code, but lacks several advanced features:

| Feature | Letta Code | Karla | Gap |
|---------|-----------|-------|-----|
| Client-side tools | ✅ Full | ✅ Full | None |
| Tool approval flow | ✅ Full | ✅ Full | None |
| Core tools (Read/Write/Edit/Bash/Grep/Glob) | ✅ | ✅ | None |
| Multiple toolsets (Anthropic/OpenAI/Gemini) | ✅ | ❌ | **High** |
| Memory blocks system | ✅ | ❌ | **High** |
| Skills system | ✅ | ⚠️ Partial | **Medium** |
| System prompt variations | ✅ | ❌ | **Medium** |
| Permission system | ✅ | ❌ | **Medium** |
| Tool hash caching | ✅ | ❌ | Low |
| Subagents/Task tool | ✅ Full | ⚠️ Stub | **Medium** |

---

## 1. Toolset System

### Letta Code

Letta Code has a sophisticated toolset system with **multiple provider-specific toolsets**:

```typescript
// From manager.ts
export const ANTHROPIC_DEFAULT_TOOLS: ToolName[] = [
  "AskUserQuestion", "Bash", "BashOutput", "Edit", "EnterPlanMode",
  "ExitPlanMode", "Glob", "Grep", "KillBash", "Read", "Skill",
  "Task", "TodoWrite", "Write",
];

export const OPENAI_DEFAULT_TOOLS: ToolName[] = [
  "shell_command", "shell", "read_file", "list_dir", "grep_files",
  "apply_patch", "update_plan", "Skill", "Task",
];

export const GEMINI_DEFAULT_TOOLS: ToolName[] = [
  "run_shell_command", "read_file_gemini", "list_directory", "glob_gemini",
  "search_file_content", "replace", "write_file_gemini", "write_todos",
  "read_many_files", "Skill", "Task",
];
```

**Key features:**
- Automatic toolset selection based on model provider
- `/toolset` command to switch between toolsets
- Tool name mapping between internal and server names
- Hash-based caching to avoid redundant upserts

### Karla

Karla has a single unified toolset:

```python
# From tools/__init__.py
def create_default_registry(working_dir: str, skills_dir: str | None = None):
    registry = ToolRegistry()
    registry.register(ReadTool(working_dir))
    registry.register(WriteTool(working_dir))
    registry.register(EditTool(working_dir))
    registry.register(BashTool())
    registry.register(BashOutputTool())
    registry.register(KillBashTool())
    registry.register(GrepTool(working_dir))
    registry.register(GlobTool(working_dir))
    # ... etc
    return registry
```

**Gap:** No provider-specific toolsets, no `/toolset` command.

---

## 2. Tool Definitions

### Letta Code

Tools have rich descriptions loaded from markdown files:

```typescript
// From toolDefinitions.ts
import ReadDescription from "./descriptions/Read.md";
import ReadSchema from "./schemas/Read.json";

const toolDefinitions = {
  Read: {
    schema: ReadSchema,
    description: ReadDescription.trim(),
    impl: read as unknown as ToolImplementation,
  },
  // ...
};
```

The descriptions are comprehensive and include:
- Usage instructions
- Examples
- Git commit instructions (in Bash)
- Security warnings

### Karla

Tools have inline descriptions in Python:

```python
# From read.py
def definition(self) -> ToolDefinition:
    return ToolDefinition(
        name="Read",
        description="""Reads a file from the local filesystem.
Assume this tool is able to read all files...
Usage:
- The file_path parameter must be an absolute path...""",
        parameters={...}
    )
```

**Gap:** Karla's descriptions are shorter and lack some guidance (e.g., git commit format).

---

## 3. Tool Permission System

### Letta Code

Sophisticated permission system with multiple scopes:

```typescript
// From manager.ts
const TOOL_PERMISSIONS: Record<ToolName, { requiresApproval: boolean }> = {
  AskUserQuestion: { requiresApproval: true },
  Bash: { requiresApproval: true },
  BashOutput: { requiresApproval: false },
  Edit: { requiresApproval: true },
  Read: { requiresApproval: false },
  // ...
};

// Permission rules can be saved per session/project/user:
export async function savePermissionRule(
  rule: string,
  ruleType: "allow" | "deny" | "ask",
  scope: "project" | "local" | "user" | "session",
  workingDirectory: string = process.cwd(),
): Promise<void>
```

### Karla

All tools use `requires_approval=True` and auto-approve:

```python
# From letta.py
def register_tools_with_letta(..., requires_approval: bool = True):
    # All tools registered with same approval setting
    tool = client.tools.upsert(
        source_code=source_code,
        json_schema=json_schema,
        default_requires_approval=requires_approval,
    )
```

**Gap:** No per-tool permission configuration, no persistent permission rules.

---

## 4. System Prompts

### Letta Code

Multiple system prompts for different providers:
- `letta_claude.md` - Anthropic-specific prompt
- `letta_codex.md` - OpenAI-specific prompt
- `letta_gemini.md` - Gemini-specific prompt

Key sections in `letta_claude.md`:
```markdown
# Tone and style
# Professional objectivity
# Planning without timelines
# Task Management
# Asking questions as you work
# Doing tasks
# Tool usage policy
# Memory
# Skills
```

### Karla

No system prompt management. Agents are created with minimal system prompts:

```python
# From test_letta_e2e.py
agent = crow_client.agents.create(
    system="You are a coding assistant with file tools...",
    # Basic instructions only
)
```

**Gap:** Need to implement system prompt templates matching Letta Code's structure.

---

## 5. Memory System

### Letta Code

Rich memory block system with Letta's memory primitives:

```typescript
// From create.ts
const defaultBaseTools = baseTools ?? [
  baseMemoryTool,      // "memory" or "memory_apply_patch"
  "web_search",
  "conversation_search",
  "fetch_webpage",
];

// Memory blocks loaded from .mdx files:
const defaultMemoryBlocks = await getDefaultMemoryBlocks();
// Blocks: persona, skills, loaded_skills, etc.
```

Memory blocks in `persona.mdx`:
```markdown
---
label: persona
description: A memory block for storing learned behavioral adaptations...
---
My name is Letta Code. I'm an AI coding assistant.
```

### Karla

No memory system integration:

```python
# Agent creation doesn't use memory blocks
agent = client.agents.create(
    name="karla-test",
    system="...",
    llm_config=config.llm.to_dict(),
    embedding="letta/letta-free",
    include_base_tools=False,  # No memory tools
)
```

**Gap:** No memory blocks, no persona system, no persistent learning.

---

## 6. Skills System

### Letta Code

Full skills system with load/unload/refresh:

```markdown
# From Skill.md description
- Use `command: "load"` with a list of skill IDs to load skills
- Use `command: "unload"` with a list of skill IDs to unload skills
- Use `command: "refresh"` to re-scan the skills directory
- Skills are loaded from the skills directory specified in the `skills` memory block
```

Skills are stored in `.skills/` directory with `SKILL.md` files.

### Karla

SkillTool exists but is a stub:

```python
# From tools/__init__.py
registry.register(SkillTool(skills_dir))
```

**Gap:** Need to implement actual skill loading/unloading with memory blocks.

---

## 7. Tool Registration

### Letta Code

Uses Python stubs with explicit JSON schemas:

```typescript
// From manager.ts
function generatePythonStub(name: string, _description: string, schema: JsonSchema): string {
  return `def ${name}(${paramList}):
    """Stub method. This tool is executed client-side via the approval flow.
    """
    raise Exception("This is a stub tool. Execution should happen on client.")
`;
}

// Registration with both stub and schema:
await client.tools.upsert({
  default_requires_approval: true,
  source_code: pythonStub,
  json_schema: fullJsonSchema,  // Explicit schema for LLM
});
```

### Karla

Same pattern implemented:

```python
# From letta.py
def register_tools_with_letta(...):
    sources = registry.to_letta_sources()  # Python stubs
    schemas = {tool.name: tool.definition().to_openai_schema(strict=True) for tool in registry}

    tool = client.tools.upsert(
        source_code=source_code,
        json_schema=json_schema,  # Explicit schema
        default_requires_approval=requires_approval,
    )
```

**Match:** Tool registration pattern is equivalent.

---

## 8. Approval/Execution Flow

### Letta Code

From `approval-execution.ts` (similar to Lares pattern):
- Sends message
- Receives `ApprovalRequestMessage`
- Executes tool locally
- Sends approval with result

### Karla

Implemented in `test_letta_e2e.py`:

```python
def send_tool_result(client, agent_id, tool_call_id, result, status="success"):
    response = client.agents.messages.create(
        agent_id=agent_id,
        messages=[{
            "type": "approval",
            "approvals": [{
                "type": "tool",
                "tool_call_id": tool_call_id,
                "tool_return": result,
                "status": status,
            }]
        }],
    )
```

**Match:** Approval flow is equivalent.

---

## Recommendations for Karla

### Priority 1: System Prompt Templates
Create `prompts/` directory with provider-specific prompts matching Letta Code:
- Include all sections: Tone/style, Task Management, Tool usage policy, etc.
- Add git commit formatting instructions to Bash tool description

### Priority 2: Memory Blocks Integration
Add memory block support:
- Persona block for behavioral adaptations
- Skills block for available skills
- Loaded_skills block for active skills
- Use Letta's built-in memory tools

### Priority 3: Multiple Toolsets
Add toolset switching for different LLM providers:
- Anthropic: snake_case tools
- OpenAI: PascalCase tools with apply_patch
- Gemini: Specific tools like replace, read_many_files

### Priority 4: Permission System
Add per-tool permissions:
- Read-only tools: no approval needed
- Write/execute tools: approval needed
- Session/project-level permission rules

### Lower Priority
- Tool hash caching for efficient re-registration
- Full Task tool with subagent support
- Skill load/unload with memory blocks

---

## Conclusion

Karla has successfully implemented the **core client-side tool execution pattern** from Letta Code. The main gaps are in:

1. **System prompts** - Need rich, provider-specific prompts
2. **Memory system** - No memory block integration
3. **Toolsets** - Single toolset vs. provider-specific
4. **Permissions** - No granular permission system

The foundational architecture (tool registration, approval flow, execution) is solid and matches Letta Code. The gaps are mostly in the "intelligence layer" - the prompts, memory, and behavioral customization that make the agent more capable.
