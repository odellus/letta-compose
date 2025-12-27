# Optimizing KV Cache for Local LLMs in Letta

## Problem Statement
Letta's memory system embeds memory blocks directly in the system prompt. When memory blocks change, the entire system prompt must be regenerated, causing cache invalidation in local LLMs like llama.cpp that cache attention patterns. This results in:
- Re-processing of all context tokens 
- Loss of cached attention patterns
- Performance degradation for locally hosted models

## Solution: Immutable System Prompt Between Compactions

### Core Insight
The system prompt should be treated as a **snapshot at session initialization**, not a live view. This mirrors how agents already understand filesystems - a directory listing in context might be stale after file operations, but the agent tracks changes through tool responses.

### Benefits
- **Full KV Cache Preservation**: System prompt unchanged between compactions
- **Agent Coherence**: No retroactive context changes confusing the model
- **Durability**: Memory still persists immediately to DB
- **Simplicity**: Minimal code changes

## Implementation (Completed)

### 1. New Agent Flag: `kv_cache_friendly`
Added to `AgentState`, `CreateAgent`, `UpdateAgent` schemas and ORM:
```python
kv_cache_friendly: Optional[bool] = Field(
    False,
    description="If set to True, the system prompt will remain immutable between compactions to preserve KV cache for local LLMs."
)
```

### 2. Memory Tool Responses Return Diffs
Modified `core_memory_append` and `core_memory_replace` to return structured responses:
```
Memory block 'persona' updated.
Operation: append
Content added: User prefers casual communication.
Characters: 847/5000
```

### 3. New `memory_read` Tool
Added tool for agents to read current memory state:
```python
async def memory_read(self, agent_state, actor, label=None) -> str:
    """Read current memory state from database."""
```

### 4. Skip System Prompt Rebuild Between Compactions
In `_rebuild_memory()` (letta_agent_v2.py):
```python
if self.agent_state.kv_cache_friendly:
    return in_context_messages  # Skip rebuild
```

In `update_memory_if_changed_async()` (agent_manager.py):
```python
if not agent_state.kv_cache_friendly:
    await self.rebuild_system_prompt_async(...)
```

### 5. Rebuild System Prompt at Compaction
In `summarizer.py`, after message eviction:
```python
if agent_state.kv_cache_friendly:
    _, new_system_message, _, _ = await self.agent_manager.rebuild_system_prompt_async(
        agent_id=self.agent_id,
        actor=self.actor,
        force=True,
    )
```

### 6. System Prompt Snapshot Note
When `kv_cache_friendly` is enabled, the system prompt includes:
```xml
<memory_snapshot_note>
The memory blocks shown above are a snapshot from session initialization or last compaction.
When you update memory using memory tools, changes are persisted immediately but reflected in tool responses, not here.
Use memory_read(label) to verify the current state of any memory block.
</memory_snapshot_note>
```

## Files Modified
- `letta/schemas/agent.py` - Added `kv_cache_friendly` field
- `letta/orm/agent.py` - Added `kv_cache_friendly` column
- `letta/services/tool_executor/core_tool_executor.py` - Diff responses, `memory_read` tool
- `letta/functions/function_sets/base.py` - `memory_read` function definition
- `letta/agents/letta_agent_v2.py` - Skip rebuild when flag enabled
- `letta/services/agent_manager.py` - Skip rebuild when flag enabled
- `letta/services/summarizer/summarizer.py` - Rebuild at compaction
- `letta/prompts/prompt_generator.py` - Snapshot note
- `letta/agents/base_agent.py` - Pass flag to prompt generator
- `alembic/versions/add_kv_cache_friendly_to_agents.py` - DB migration

## Usage
```python
# Create agent with KV cache friendly mode
agent = client.agents.create(
    name="my-agent",
    kv_cache_friendly=True,  # Enable immutable system prompt
    ...
)
```

## Mental Model for the Agent
```
System prompt = "who you were when you woke up"
Tool responses = "what changed and when"  
Conversation history = accurate record of decisions given context at each moment
```

The agent can reason: "I started believing X (visible in system prompt), which is why I did Y. Then I learned Z (visible in tool response) and updated my memory. Now I believe Z."
