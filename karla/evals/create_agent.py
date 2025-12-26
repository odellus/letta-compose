"""Agent factory for karla eval agents.

Creates a fresh karla agent for each test sample with all karla tools attached.
Uses the actual karla tool registry - same tools tested in the main codebase.
"""

from letta_client import AsyncLetta
from letta_client.types import CreateBlockParam
from letta_evals.decorators import agent_factory
from letta_evals.models import Sample

from karla.tools import create_default_registry

# Default LLM config for local testing
DEFAULT_LLM_CONFIG = {
    "model": (
        "/home/thomas-wood/.cache/llama.cpp/"
        "lmstudio-community_Qwen3-Coder-30B-A3B-Instruct-GGUF_"
        "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
    ),
    "model_endpoint": "http://coast-after-3:1234/v1",
    "model_endpoint_type": "openai",
    "context_window": 119000,
}

DEFAULT_EMBEDDING = "ollama/mxbai-embed-large:latest"

KARLA_SYSTEM_PROMPT = """You are Karla, a coding assistant agent.

You have access to tools for reading, writing, and editing files, as well as running bash commands.
Use these tools to help the user with their coding tasks.

When asked to perform a task:
1. Think about what tools you need
2. Execute the necessary tool calls
3. Report the results clearly

Always be precise and verify your work."""


async def register_tools_with_letta(
    client: AsyncLetta,
    agent_id: str,
    working_dir: str,
) -> list[str]:
    """Register karla tools with a Letta agent.

    Uses the actual karla tool registry with proper strict-mode schemas.
    """
    registry = create_default_registry(working_dir)

    registered = []
    tool_ids = []

    # Get source code and schemas from registry
    sources = registry.to_letta_sources(strict=True)
    schemas = {tool.name: tool.definition().to_openai_schema(strict=True) for tool in registry}

    for name, source_code in sources.items():
        try:
            # Build json_schema in Letta's expected format
            openai_schema = schemas.get(name, {})
            func_schema = openai_schema.get("function", {})

            json_schema = {
                "name": name,
                "description": func_schema.get("description", ""),
                "parameters": func_schema.get("parameters", {}),
            }

            tool = await client.tools.upsert(
                source_code=source_code,
                json_schema=json_schema,
                default_requires_approval=True,
            )
            registered.append(name)
            tool_ids.append(tool.id)
        except Exception as e:
            print(f"Failed to register tool {name}: {e}")

    # Attach tools to the agent
    for tool_id in tool_ids:
        try:
            await client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
        except Exception:
            pass

    return registered


@agent_factory
async def create_karla_agent(client: AsyncLetta, sample: Sample) -> str:
    """Create a fresh karla agent for evaluation.

    Each test sample gets a brand new agent with no prior memory/history.
    This is the letta-evals equivalent of torch.no_grad() - memories don't persist.
    """
    working_dir = "/tmp/karla-eval"
    if sample.agent_args and "working_dir" in sample.agent_args:
        working_dir = sample.agent_args["working_dir"]

    agent = await client.agents.create(
        name=f"karla-eval-{sample.id}",
        agent_type="letta_v1_agent",
        system=KARLA_SYSTEM_PROMPT,
        llm_config=DEFAULT_LLM_CONFIG,
        embedding=DEFAULT_EMBEDDING,
        memory_blocks=[
            CreateBlockParam(
                label="persona",
                value="I am Karla, a helpful coding assistant.",
            ),
            CreateBlockParam(
                label="human",
                value="The user is a developer running evaluation tests.",
            ),
            CreateBlockParam(
                label="working_context",
                value=f"Current working directory: {working_dir}",
            ),
        ],
        include_base_tools=False,
        kv_cache_friendly=True,
    )

    # Register actual karla tools
    await register_tools_with_letta(client, agent.id, working_dir)

    return agent.id
