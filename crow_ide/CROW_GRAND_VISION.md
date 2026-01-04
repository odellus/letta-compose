# Crow: The Grand Vision

## What is Crow?

Crow is not just an IDE. It's a complete stack for **human-out-of-the-loop autonomous coding**.

The goal: You plan your project, describe what you want to build, and then an agent works on it for hours, days, weeks - while you're free. Not babysitting. Not holding its hand. Actually free.

## The Stack

Crow is five components working together:

### 1. llama.cpp (future: hipified Candle)
Local LLM inference. No API costs. Throughput over accuracy - when you're not paying per token, you can let it iterate forever. Current bottleneck is speed, not money.

Future plan: Replace with a hipified Candle fork for AMD GPU support and tighter integration.

### 2. Letta (forked)
Memory and agent management layer. The fork adds a flag that fundamentally changes how it operates - enabling the kind of persistent, autonomous agent behavior we need.

Letta gives us:
- Persistent memory across sessions
- Agent personality that survives restarts
- The foundation for distinct agent personas (validator vs fixer)

### 3. letta-python (forked)
Python SDK modifications to support the Letta fork changes.

### 4. Karla
A Letta agent defined in Python with the same tool surface as Claude Code / Open Code:
- File read/write/edit
- Bash execution
- Glob/Grep search
- Web fetch
- Task spawning
- Todo tracking
- Plan mode

Karla is the agent personality. With Letta's memory, Karla can have opinions, preferences, and accumulated wisdom about the codebase.

### 5. crow-ide
A marimo-inspired minimalist web IDE. Features:
- File tree navigation
- Agent chat panel with ACP protocol
- Integrated terminal
- Workspace switching
- Sticky todo panel for task tracking

Together, these ARE Crow.

## The Dream: Coagents with Distinct Personalities

The key insight: you need two personalities working together:

### The Fixer
- Inclined to write code, solve problems, implement features
- Optimistic, builder mentality
- "I can make this work"

### The Validator
- Inclined to test, inspect, poke holes, break things
- Skeptical, destructive (in a good way)
- "Prove it actually works"

With Letta's personality and memory system, we can finally create agents that are genuinely distinct - not just different prompts, but different accumulated experiences and tendencies.

The Ralph Loop was the first attempt at this but it doesn't work as a simple loop. It needs the adversarial dynamic.

## The Distillation Pipeline

1. **Claude Code + Langfuse**: Every Claude Code session gets logged to Langfuse
2. **Gold Data**: These logs become training data - real problem-solving trajectories from a frontier model
3. **AGENTS.md Evolution**: Distill patterns into agent instructions
4. **Local Model Training**: Eventually, train local models on these trajectories

The logs are gold because they capture:
- How Claude approaches novel problems
- Tool use patterns that work
- Recovery from mistakes
- The "feel" of good agentic coding

## Throughput vs Accuracy Tradeoff

With local LLMs:
- **No cost per token** - iterate as much as you want
- **Time is the constraint** - Qwen3-80B is slow (~50s per response)
- **Accuracy matters more** - fewer iterations means each one counts

This is why models like IQuest-Coder-V1-40B-Loop-Instruct are interesting:
- Recurrent transformer with shared parameters (2 iterations)
- Trained on "code-flow" - repository evolution, commit transitions
- Multi-agent role-playing for synthetic tool-use data
- Could be the right accuracy/efficiency tradeoff for autonomous loops

## Why Not Just Use Claude/GPT?

1. **Cost**: Human-out-of-loop means LOTS of tokens. API costs explode.
2. **Control**: Local means you control the model, the prompts, the fine-tuning
3. **Speed**: Paradoxically, local can be faster for long sessions (no rate limits)
4. **Privacy**: Your code never leaves your machine
5. **The Vision**: Eventually, custom models trained on YOUR coding patterns

## The Polyglingual Reality

The codebase is:
- Python (Karla, Letta integration)
- TypeScript/React (crow-ide frontend)
- Rust (crow_agent, future Candle work)

And that's fine. Agents don't care what language it's in. That's the whole point. That's why everyone is writing everything in TypeScript now - the humans need consistency, but the agents just figure it out.

## Current State

- [x] llama.cpp running with Qwen3-80B
- [x] Letta server with forked modifications
- [x] Karla agent with full Claude Code tool surface
- [x] crow-ide with file tree, agent panel, terminal
- [x] ACP protocol integration
- [x] Workspace switching
- [x] Todo panel for task tracking
- [x] Session persistence
- [ ] Langfuse integration for logging
- [ ] Coagent adversarial loop (Fixer + Validator)
- [ ] Automatic validation pipeline
- [ ] Custom model training on collected trajectories
- [ ] hipified Candle integration

## The End State

You wake up. You have an idea. You write it down - what you want to build, why, the constraints, the vibes. You hit go.

You go live your life.

Hours later, you come back. There's a PR. Tests pass. The code works. The agent left notes about tradeoffs it made and questions it has.

You review, you tweak, you merge. You have a conversation about the next feature.

That's the dream. That's Crow.

---

## References

- [IQuest-Coder-V1 GitHub](https://github.com/IQuestLab/IQuest-Coder-V1) - Interesting model architecture
- [IQuest-Coder Loop Model](https://huggingface.co/IQuestLab/IQuest-Coder-V1-40B-Loop-Instruct) - Recurrent transformer for efficiency
- "Close the Loop: Synthesizing Infinite Tool-Use Data via Multi-Agent Role-Playing" (arXiv:2512.23611) - Relevant to coagent training
- [Agent Client Protocol](https://agentclientprotocol.com/) - ACP integration
- [Marimo](https://marimo.io/) - Inspiration for IDE minimalism
