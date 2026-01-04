# Karla - Claude Code Guide

## Package Manager: uv

This project uses **uv** - an extremely fast Python package manager written in Rust.

### CRITICAL: Activate venv and use `uv run`

**ALWAYS** cd to the project directory and activate the virtual environment first:

```bash
# Step 1: cd to karla directory
cd /home/thomas/src/projects/letta-proj/karla

# Step 2: Activate the virtual environment
. .venv/bin/activate

# Step 3: Now use uv run
uv run python scripts/langfuse_traces.py
```

**One-liner pattern:**
```bash
cd /home/thomas/src/projects/letta-proj/karla && . .venv/bin/activate && uv run python scripts/langfuse_traces.py
```

### WRONG vs RIGHT

```bash
# WRONG - never do this
python scripts/langfuse_traces.py
uv run python scripts/langfuse_traces.py  # without activating venv first!

# RIGHT - activate venv then use uv run
cd /home/thomas/src/projects/letta-proj/karla && . .venv/bin/activate && uv run python scripts/langfuse_traces.py
cd /home/thomas/src/projects/letta-proj/karla && . .venv/bin/activate && uv run pytest
```

### Common uv Commands

```bash
# Sync dependencies (install from pyproject.toml + uv.lock)
uv sync

# Add a new dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run any command in the project environment
uv run <command>

# Run Python scripts
uv run python script.py

# Run pytest
uv run pytest

# Run the CLI
uv run karla-cli
uv run karla-acp
```

### Why uv?

- 10-100x faster than pip
- Manages Python versions, virtualenvs, and dependencies in one tool
- Lock file (uv.lock) ensures reproducible installs
- No need to manually activate virtualenvs - `uv run` handles it

## Project Scripts

```bash
# List Langfuse traces
uv run python scripts/langfuse_traces.py

# Get specific trace
uv run python scripts/langfuse_traces.py <trace_id>

# Get LLM calls as JSON
uv run python scripts/langfuse_traces.py <trace_id> --llm

# Run tests
uv run pytest

# Run linter
uv run ruff check .
```

## CLI Entry Points

Defined in pyproject.toml:
- `karla-cli` - Interactive CLI (`uv run karla-cli`)
- `karla-acp` - ACP server (`uv run karla-acp`)

## Running the System

### Prerequisites
1. Letta server running on port 8283
2. LM Studio (local LLM) running
3. Langfuse (optional, for tracing) on port 3044

### Start Commands

```bash
# Terminal 1: Run the ACP server
cd /home/thomas/src/projects/letta-proj/karla
uv run karla-acp

# Or with stdio-to-ws for WebSocket bridging
npx stdio-to-ws "uv run karla-acp" --port 3000
```

## Configuration

- `karla.yaml` - LLM and server configuration
- `.env` - API keys and secrets (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, etc.)

## Debugging

### Check Langfuse traces
```bash
# Recent traces
uv run python scripts/langfuse_traces.py --last 10

# Specific trace observations
uv run python scripts/langfuse_traces.py <trace_id> -o

# LLM request/response as JSON
uv run python scripts/langfuse_traces.py <trace_id> --llm | jq .
```

### Local LLM is SLOW
The local LLM (Qwen3-80B via LM Studio) takes 30-120 seconds per response. This is normal. Don't assume it's broken - wait.
