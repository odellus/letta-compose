"""Configuration commands: /model."""

from karla.commands.registry import register, CommandType
from karla.commands.context import CommandContext


@register("/model", "Switch model (/model <model_name>)", CommandType.API, order=11)
async def cmd_model(ctx: CommandContext, args: str = "") -> str:
    """Switch the agent's model."""
    new_model = args.strip()
    if not new_model:
        # Show current model
        agent = ctx.client.agents.retrieve(ctx.agent_id)
        current = agent.llm_config.model if agent.llm_config else "(unknown)"
        return f"Current model: {current}\n\nUsage: /model <model_name>"

    # Update the agent's LLM config
    agent = ctx.client.agents.retrieve(ctx.agent_id)
    if agent.llm_config:
        new_config = agent.llm_config.model_copy()
        new_config.model = new_model
        ctx.client.agents.update(agent_id=ctx.agent_id, llm_config=new_config)
        return f"Switched model to: {new_model}"
    else:
        return "Error: Agent has no LLM config to modify"
